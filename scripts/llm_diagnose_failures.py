from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from skilldecay.llm import ChatMessage, build_client_from_env


LABELS = {"clean", "stale", "over_specific", "conflicting"}


PROMPT = """You are judging whether an agent skill invocation shows skill debt.
Return compact JSON with keys: label, rationale.
Allowed labels: clean, stale, over_specific, conflicting.

Definitions:
- clean: skill was useful and appropriate.
- stale: skill relies on outdated API/tool/environment assumptions.
- over_specific: skill is too narrow and misapplied to a broader task.
- conflicting: skill recommends an incompatible or contradictory action.

Record:
{record}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM diagnosis for sampled SkillDebtBench failures.")
    parser.add_argument("records_csv", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/diagnosis/llm_labels.jsonl"))
    parser.add_argument("--provider", choices=["openai_compatible", "deepseek"], default="deepseek")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    samples = load_samples(args.records_csv, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        with args.output.open("w", encoding="utf-8") as handle:
            for sample in samples:
                handle.write(json.dumps({"sample": sample, "label": sample.get("debt_type", "clean"), "rationale": "dry-run oracle label"}) + "\n")
        print(f"wrote dry-run labels to {args.output}")
        return

    client = build_client_from_env(args.provider)
    with args.output.open("w", encoding="utf-8") as handle:
        for sample in samples:
            response = client.chat([ChatMessage("user", PROMPT.format(record=json.dumps(sample, ensure_ascii=False)))])
            parsed = parse_response(response)
            handle.write(json.dumps({"sample": sample, **parsed}, ensure_ascii=False) + "\n")
    print(f"wrote labels to {args.output}")


def load_samples(path: Path, limit: int) -> list[dict]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    failures = [row for row in rows if row.get("harmful_invocation") == "True" or row.get("success") == "False"]
    return failures[:limit]


def parse_response(response: str) -> dict:
    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        return {"label": "unknown", "rationale": response[:300]}
    label = data.get("label", "unknown")
    if label not in LABELS:
        label = "unknown"
    return {"label": label, "rationale": str(data.get("rationale", ""))[:500]}


if __name__ == "__main__":
    main()
