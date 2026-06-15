from __future__ import annotations

from dataclasses import dataclass
import json
import os
import urllib.error
import urllib.request


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass
class LLMClient:
    provider: str
    api_key_env: str
    base_url_env: str | None = None
    default_base_url: str | None = None
    default_model: str = "gpt-4o-mini"
    timeout_seconds: int = 60

    def chat(self, messages: list[ChatMessage], model: str | None = None, temperature: float = 0.0) -> str:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"missing environment variable: {self.api_key_env}")
        base_url = os.getenv(self.base_url_env) if self.base_url_env else self.default_base_url
        if not base_url:
            raise RuntimeError("missing base URL for chat client")
        endpoint = base_url.rstrip("/") + "/v1/chat/completions"
        payload = {
            "model": model or self.default_model,
            "messages": [message.__dict__ for message in messages],
            "temperature": temperature,
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM request failed: {error.code} {body}") from error
        return data["choices"][0]["message"]["content"]


def build_client_from_env(provider: str) -> LLMClient:
    if provider == "openai_compatible":
        return LLMClient(
            provider=provider,
            api_key_env="OPENAI_API_KEY",
            base_url_env="OPENAI_BASE_URL",
            default_base_url="https://api.openai.com",
            default_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )
    if provider == "deepseek":
        return LLMClient(
            provider=provider,
            api_key_env="DEEPSEEK_API_KEY",
            default_base_url="https://api.deepseek.com",
            default_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        )
    raise ValueError(f"unknown provider: {provider}")
