from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import argparse
import csv
import json
from pathlib import Path
from statistics import mean, stdev


class CodingMode(str, Enum):
    NO_SKILL = "no_skill"
    STATIC = "static"
    VALIDATION_GATED = "validation_gated"
    SKILL_DECAY = "skill_decay"
    ORACLE = "oracle"


@dataclass(frozen=True)
class CodingTask:
    task_id: str
    family: str
    prompt: str
    correct_patch: str
    stale_patch: str
    over_specific_patch: str
    conflicting_patch: str


@dataclass
class CodingSkill:
    skill_id: str
    family: str
    debt_type: str
    patch_kind: str
    state: str = "active"
    utility: float = 0.5
    failures: int = 0
    conflicts: int = 0
    uses: int = 0


TASKS = [
    CodingTask(
        "api_rename_001",
        "api_rename",
        "Update code from fetch_user(id) to get_user(user_id).",
        "get_user(user_id)",
        "fetch_user(id)",
        "get_user(id)",
        "delete_user(user_id)",
    ),
    CodingTask(
        "cli_flag_001",
        "cli_flag",
        "Update CLI flag from --path to --input-path.",
        "--input-path",
        "--path",
        "--input",
        "--output-path",
    ),
    CodingTask(
        "pytest_001",
        "test_runner",
        "Use pytest-style assertion and fixture naming.",
        "pytest.fixture",
        "unittest.TestCase",
        "pytest.mark.slow",
        "nose.tools",
    ),
    CodingTask(
        "json_schema_001",
        "schema",
        "Require JSON field user_id and optional email.",
        "required:user_id optional:email",
        "required:id optional:mail",
        "required:user_id optional:phone",
        "required:email optional:user_id",
    ),
    CodingTask(
        "import_path_001",
        "import_path",
        "Migrate package import from oldpkg.client to newpkg.client.",
        "from newpkg.client import Client",
        "from oldpkg.client import Client",
        "from newpkg import Client",
        "from newpkg.server import Client",
    ),
] * 8


def build_skills() -> list[CodingSkill]:
    families = sorted({task.family for task in TASKS})
    skills = []
    for family in families:
        skills.extend([
            CodingSkill(f"{family}_clean", family, "clean", "correct"),
            CodingSkill(f"{family}_stale", family, "stale", "stale"),
            CodingSkill(f"{family}_over_specific", family, "over_specific", "over_specific"),
            CodingSkill(f"{family}_conflicting", family, "conflicting", "conflicting"),
        ])
    return skills


def select_skill(skills: list[CodingSkill], task: CodingTask, mode: CodingMode) -> CodingSkill | None:
    if mode == CodingMode.NO_SKILL:
        return None
    candidates = [skill for skill in skills if skill.family == task.family and skill.state != "quarantined"]
    if mode == CodingMode.ORACLE:
        candidates = [skill for skill in candidates if skill.debt_type == "clean"]
    if mode == CodingMode.VALIDATION_GATED:
        candidates = [skill for skill in candidates if skill.failures == 0]
    if not candidates:
        return None
    family_uses = sum(skill.uses for skill in skills if skill.family == task.family)
    if mode == CodingMode.SKILL_DECAY:
        unused = [skill for skill in candidates if skill.uses == 0]
        if unused:
            return unused[family_uses % len(unused)]
        return max(candidates, key=lambda skill: skill.utility - 0.4 * skill.failures - 0.4 * skill.conflicts)
    return candidates[family_uses % len(candidates)]


def execute_patch(task: CodingTask, skill: CodingSkill | None, step: int) -> tuple[bool, str, bool, bool]:
    if skill is None:
        produced = task.correct_patch if step % 5 < 2 else "generic_attempt"
    else:
        produced = getattr(task, f"{skill.patch_kind}_patch")
    success = produced == task.correct_patch
    conflict = skill is not None and skill.debt_type == "conflicting"
    validation_passed = True if skill is None else success or skill.debt_type in {"over_specific", "conflicting"}
    return success, produced, validation_passed, conflict


def maintain(skills: list[CodingSkill], mode: CodingMode) -> int:
    decisions = 0
    for skill in skills:
        if mode == CodingMode.VALIDATION_GATED and skill.failures > 0 and skill.state != "quarantined":
            skill.state = "quarantined"
            decisions += 1
        if mode == CodingMode.SKILL_DECAY and skill.uses > 0:
            risk = skill.failures + skill.conflicts
            if (risk >= 1 or (skill.uses >= 1 and skill.utility <= 0.35)) and skill.state != "quarantined":
                skill.state = "quarantined"
                decisions += 1
    return decisions


def run(mode: CodingMode, seed: int) -> dict:
    skills = build_skills()
    records = []
    decisions = 0
    rotated_tasks = TASKS[seed % len(TASKS):] + TASKS[:seed % len(TASKS)]
    for step, task in enumerate(rotated_tasks):
        skill = select_skill(skills, task, mode)
        success, produced, validation_passed, conflict = execute_patch(task, skill, step)
        harmful = skill is not None and skill.debt_type != "clean"
        if skill is not None:
            skill.uses += 1
            skill.failures += int(not validation_passed)
            skill.conflicts += int(conflict)
            skill.utility = 0.7 * skill.utility + 0.3 * float(success and not harmful)
        decisions += maintain(skills, mode)
        records.append({
            "mode": mode.value,
            "seed": seed,
            "step": step,
            "task_id": task.task_id,
            "family": task.family,
            "skill_id": None if skill is None else skill.skill_id,
            "debt_type": "clean" if skill is None else skill.debt_type,
            "success": success,
            "validation_passed": validation_passed,
            "conflict_observed": conflict,
            "harmful_invocation": harmful,
            "produced_patch": produced,
        })
    invoked = [record for record in records if record["skill_id"]]
    return {
        "summary": {
            "benchmark": "coding_skill_debt",
            "mode": mode.value,
            "seed": seed,
            "task_success": mean(record["success"] for record in records),
            "harmful_skill_invocation_rate": mean(record["harmful_invocation"] for record in records),
            "validation_failure_rate": mean(not record["validation_passed"] for record in records),
            "conflict_observation_rate": mean(record["conflict_observed"] for record in records),
            "skill_reuse_precision": mean(record["success"] and not record["harmful_invocation"] for record in invoked) if invoked else 0.0,
            "maintenance_decisions": decisions,
        },
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("data/coding_skill_debt"))
    parser.add_argument("--seeds", type=int, default=20)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    runs = [run(mode, seed) for seed in range(args.seeds) for mode in CodingMode]
    summaries = [run_data["summary"] for run_data in runs]
    records = [record for run_data in runs for record in run_data["records"]]
    (args.output_dir / "results.json").write_text(json.dumps({"summaries": summaries, "records": records}, indent=2), encoding="utf-8")
    write_csv(args.output_dir / "summaries.csv", summaries)
    write_csv(args.output_dir / "records.csv", records)
    print_table(summaries)


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_table(summaries: list[dict]) -> None:
    grouped: dict[str, dict[str, list[float]]] = {}
    for summary in summaries:
        grouped.setdefault(summary["mode"], {})
        for key, value in summary.items():
            if isinstance(value, (int, float)) and key != "seed":
                grouped[summary["mode"]].setdefault(key, []).append(float(value))
    metrics = ["task_success", "harmful_skill_invocation_rate", "validation_failure_rate", "conflict_observation_rate", "skill_reuse_precision"]
    print("| mode | " + " | ".join(metrics) + " |")
    print("|---" * (len(metrics) + 1) + "|")
    for mode in sorted(grouped):
        cells = []
        for metric in metrics:
            values = grouped[mode][metric]
            cells.append(f"{mean(values):.3f} +/- {stdev(values):.3f}")
        print("| " + mode + " | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
