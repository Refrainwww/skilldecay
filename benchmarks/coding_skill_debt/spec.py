"""Coding SkillDebtBench placeholder.

This module defines the intended interface for the next phase: concrete coding
repositories with tests, polluted skill libraries, and executable validators.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodingTaskSpec:
    task_id: str
    repo_path: Path
    prompt: str
    test_command: str
    expected_debt_type: str


@dataclass(frozen=True)
class CodingSkillSpec:
    skill_id: str
    content: str
    debt_type: str
    trigger: str


BENCHMARK_DESIGN = {
    "stale": "old API usage, renamed CLI flags, outdated package paths",
    "over_specific": "repo-specific workaround retrieved for similar but incompatible tasks",
    "conflicting": "skills that recommend incompatible test frameworks or patch locations",
}
