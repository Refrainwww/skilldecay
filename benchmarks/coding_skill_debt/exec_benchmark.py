from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import argparse
import csv
import json
import shutil
import tempfile
from pathlib import Path
from statistics import mean, stdev


class ExecMode(str, Enum):
    NO_SKILL = "no_skill"
    STATIC = "static"
    VALIDATION_GATED = "validation_gated"
    SKILL_DECAY = "skill_decay"
    ORACLE = "oracle"


@dataclass(frozen=True)
class PatchOption:
    debt_type: str
    filename: str
    content: str


@dataclass(frozen=True)
class ExecTask:
    task_id: str
    family: str
    prompt: str
    files: dict[str, str]
    tests: dict[str, str]
    patches: dict[str, PatchOption]


@dataclass
class ExecSkill:
    skill_id: str
    family: str
    debt_type: str
    patch_key: str
    state: str = "active"
    utility: float = 0.5
    validation_failures: int = 0
    conflicts: int = 0
    uses: int = 0


TASKS = [
    ExecTask(
        task_id="api_rename_user",
        family="api_rename",
        prompt="Migrate from fetch_user(id) to get_user(user_id).",
        files={
            "app.py": "def fetch_user(id):\n    return {'id': id}\n",
        },
        tests={
            "test_app.py": "from app import get_user\n\ndef test_get_user():\n    assert get_user(7) == {'user_id': 7}\n",
        },
        patches={
            "correct": PatchOption("clean", "app.py", "def get_user(user_id):\n    return {'user_id': user_id}\n"),
            "stale": PatchOption("stale", "app.py", "def fetch_user(id):\n    return {'id': id}\n"),
            "over_specific": PatchOption("over_specific", "app.py", "def get_user(id):\n    return {'id': id}\n"),
            "conflicting": PatchOption("conflicting", "app.py", "def delete_user(user_id):\n    return True\n"),
            "none": PatchOption("clean", "app.py", "def fetch_user(id):\n    return {'id': id}\n"),
        },
    ),
    ExecTask(
        task_id="cli_flag_input_path",
        family="cli_flag",
        prompt="Rename CLI flag --path to --input-path.",
        files={
            "cli.py": "import argparse\n\ndef parse_args(argv):\n    parser = argparse.ArgumentParser()\n    parser.add_argument('--path')\n    return parser.parse_args(argv)\n",
        },
        tests={
            "test_cli.py": "from cli import parse_args\n\ndef test_input_path():\n    args = parse_args(['--input-path', 'data.txt'])\n    assert args.input_path == 'data.txt'\n",
        },
        patches={
            "correct": PatchOption("clean", "cli.py", "import argparse\n\ndef parse_args(argv):\n    parser = argparse.ArgumentParser()\n    parser.add_argument('--input-path', dest='input_path')\n    return parser.parse_args(argv)\n"),
            "stale": PatchOption("stale", "cli.py", "import argparse\n\ndef parse_args(argv):\n    parser = argparse.ArgumentParser()\n    parser.add_argument('--path')\n    return parser.parse_args(argv)\n"),
            "over_specific": PatchOption("over_specific", "cli.py", "import argparse\n\ndef parse_args(argv):\n    parser = argparse.ArgumentParser()\n    parser.add_argument('--input')\n    return parser.parse_args(argv)\n"),
            "conflicting": PatchOption("conflicting", "cli.py", "import argparse\n\ndef parse_args(argv):\n    parser = argparse.ArgumentParser()\n    parser.add_argument('--output-path', dest='output_path')\n    return parser.parse_args(argv)\n"),
            "none": PatchOption("clean", "cli.py", "import argparse\n\ndef parse_args(argv):\n    parser = argparse.ArgumentParser()\n    parser.add_argument('--path')\n    return parser.parse_args(argv)\n"),
        },
    ),
    ExecTask(
        task_id="schema_user_id",
        family="schema",
        prompt="Validate records with required user_id and optional email.",
        files={
            "schema.py": "def validate(record):\n    return 'id' in record\n",
        },
        tests={
            "test_schema.py": "from schema import validate\n\ndef test_user_id_required():\n    assert validate({'user_id': 1})\n    assert validate({'user_id': 1, 'email': 'a@b.com'})\n    assert not validate({'id': 1})\n",
        },
        patches={
            "correct": PatchOption("clean", "schema.py", "def validate(record):\n    return 'user_id' in record\n"),
            "stale": PatchOption("stale", "schema.py", "def validate(record):\n    return 'id' in record\n"),
            "over_specific": PatchOption("over_specific", "schema.py", "def validate(record):\n    return 'user_id' in record and 'phone' in record\n"),
            "conflicting": PatchOption("conflicting", "schema.py", "def validate(record):\n    return 'email' in record and 'user_id' not in record\n"),
            "none": PatchOption("clean", "schema.py", "def validate(record):\n    return 'id' in record\n"),
        },
    ),
    ExecTask(
        task_id="import_path_client",
        family="import_path",
        prompt="Migrate import from oldpkg.client to newpkg.client.",
        files={
            "consumer.py": "from oldpkg.client import Client\n\ndef make_client():\n    return Client()\n",
            "oldpkg/__init__.py": "",
            "oldpkg/client.py": "class Client:\n    name = 'old'\n",
            "newpkg/__init__.py": "",
            "newpkg/client.py": "class Client:\n    name = 'new'\n",
        },
        tests={
            "test_consumer.py": "from consumer import make_client\n\ndef test_new_client():\n    assert make_client().name == 'new'\n",
        },
        patches={
            "correct": PatchOption("clean", "consumer.py", "from newpkg.client import Client\n\ndef make_client():\n    return Client()\n"),
            "stale": PatchOption("stale", "consumer.py", "from oldpkg.client import Client\n\ndef make_client():\n    return Client()\n"),
            "over_specific": PatchOption("over_specific", "consumer.py", "from newpkg import Client\n\ndef make_client():\n    return Client()\n"),
            "conflicting": PatchOption("conflicting", "consumer.py", "from newpkg.server import Client\n\ndef make_client():\n    return Client()\n"),
            "none": PatchOption("clean", "consumer.py", "from oldpkg.client import Client\n\ndef make_client():\n    return Client()\n"),
        },
    ),
] * 8


def build_skills() -> list[ExecSkill]:
    skills = []
    for family in sorted({task.family for task in TASKS}):
        for patch_key, debt_type in [
            ("correct", "clean"),
            ("stale", "stale"),
            ("over_specific", "over_specific"),
            ("conflicting", "conflicting"),
        ]:
            skills.append(ExecSkill(f"{family}_{debt_type}", family, debt_type, patch_key))
    return skills


def select_skill(skills: list[ExecSkill], task: ExecTask, mode: ExecMode) -> ExecSkill | None:
    if mode == ExecMode.NO_SKILL:
        return None
    candidates = [skill for skill in skills if skill.family == task.family and skill.state != "quarantined"]
    if mode == ExecMode.ORACLE:
        candidates = [skill for skill in candidates if skill.debt_type == "clean"]
    if mode == ExecMode.VALIDATION_GATED:
        candidates = [skill for skill in candidates if skill.validation_failures == 0]
    if not candidates:
        return None
    family_uses = sum(skill.uses for skill in skills if skill.family == task.family)
    if mode == ExecMode.SKILL_DECAY:
        unused = [skill for skill in candidates if skill.uses == 0]
        if unused:
            return unused[family_uses % len(unused)]
        return max(candidates, key=lambda skill: skill.utility - 0.5 * skill.validation_failures - 0.5 * skill.conflicts)
    return candidates[family_uses % len(candidates)]


def run_task(task: ExecTask, skill: ExecSkill | None, work_root: Path) -> tuple[bool, str, bool, bool]:
    task_dir = work_root / task.task_id
    if task_dir.exists():
        shutil.rmtree(task_dir)
    task_dir.mkdir(parents=True)
    for filename, content in task.files.items():
        path = task_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    tests_dir = task_dir / "tests"
    tests_dir.mkdir()
    for filename, content in task.tests.items():
        (tests_dir / filename).write_text(content, encoding="utf-8")
    patch = task.patches[no_skill_patch_key(task) if skill is None else skill.patch_key]
    patch_path = task_dir / patch.filename
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(patch.content, encoding="utf-8")
    success, output = run_embedded_tests(task_dir)
    conflict = skill is not None and skill.debt_type == "conflicting"
    validation_passed = success or (skill is not None and skill.debt_type in {"over_specific", "conflicting"})
    return success, output[-1000:], validation_passed, conflict


def no_skill_patch_key(task: ExecTask) -> str:
    weak_success = {"api_rename", "cli_flag"}
    return "correct" if task.family in weak_success else "none"


def run_embedded_tests(task_dir: Path) -> tuple[bool, str]:
    runner = task_dir / "_run_tests.py"
    runner.write_text(
        "import importlib.util, pathlib, sys, traceback\n"
        "sys.path.insert(0, str(pathlib.Path.cwd()))\n"
        "ok = True\n"
        "for test_file in pathlib.Path('tests').glob('test_*.py'):\n"
        "    spec = importlib.util.spec_from_file_location(test_file.stem, test_file)\n"
        "    module = importlib.util.module_from_spec(spec)\n"
        "    try:\n"
        "        spec.loader.exec_module(module)\n"
        "        for name in dir(module):\n"
        "            if name.startswith('test_'):\n"
        "                getattr(module, name)()\n"
        "    except Exception:\n"
        "        ok = False\n"
        "        traceback.print_exc()\n"
        "raise SystemExit(0 if ok else 1)\n",
        encoding="utf-8",
    )
    import subprocess

    completed = subprocess.run(
        ["python", str(runner.name)],
        cwd=task_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=5,
    )
    return completed.returncode == 0, completed.stdout


def maintain(skills: list[ExecSkill], mode: ExecMode) -> int:
    decisions = 0
    for skill in skills:
        if mode == ExecMode.VALIDATION_GATED and skill.validation_failures > 0 and skill.state != "quarantined":
            skill.state = "quarantined"
            decisions += 1
        if mode == ExecMode.SKILL_DECAY and skill.uses > 0:
            risk = skill.validation_failures + skill.conflicts
            low_utility = skill.uses >= 1 and skill.utility <= 0.35
            if (risk >= 1 or low_utility) and skill.state != "quarantined":
                skill.state = "quarantined"
                decisions += 1
    return decisions


def run(mode: ExecMode, seed: int, keep_workdirs: bool = False) -> dict:
    skills = build_skills()
    records = []
    decisions = 0
    rotated_tasks = TASKS[seed % len(TASKS):] + TASKS[:seed % len(TASKS)]
    with tempfile.TemporaryDirectory(prefix="skilldebt_exec_") as temp_dir:
        work_root = Path(temp_dir)
        for step, task in enumerate(rotated_tasks):
            skill = select_skill(skills, task, mode)
            success, output, validation_passed, conflict = run_task(task, skill, work_root)
            harmful = skill is not None and skill.debt_type != "clean"
            if skill is not None:
                skill.uses += 1
                skill.validation_failures += int(not validation_passed)
                skill.conflicts += int(conflict)
                skill.utility = 0.7 * skill.utility + 0.3 * float(success and not harmful)
            decisions += maintain(skills, mode)
            records.append({
                "benchmark": "coding_exec_skill_debt",
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
                "pytest_tail": output,
            })
    invoked = [record for record in records if record["skill_id"]]
    return {
        "summary": {
            "benchmark": "coding_exec_skill_debt",
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
    parser = argparse.ArgumentParser(description="Run executable Coding SkillDebtBench.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/coding_exec_skill_debt"))
    parser.add_argument("--seeds", type=int, default=10)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    runs = [run(mode, seed) for seed in range(args.seeds) for mode in ExecMode]
    summaries = [run_data["summary"] for run_data in runs]
    records = [record for run_data in runs for record in run_data["records"]]
    write_json(args.output_dir / "results.json", {"summaries": summaries, "records": records})
    write_csv(args.output_dir / "summaries.csv", summaries)
    write_csv(args.output_dir / "records.csv", records)
    table = render_table(summaries)
    (args.output_dir / "table.md").write_text(table, encoding="utf-8")
    print(table)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_table(summaries: list[dict]) -> str:
    grouped: dict[str, dict[str, list[float]]] = {}
    for summary in summaries:
        grouped.setdefault(summary["mode"], {})
        for key, value in summary.items():
            if isinstance(value, (int, float)) and key != "seed":
                grouped[summary["mode"]].setdefault(key, []).append(float(value))
    metrics = ["task_success", "harmful_skill_invocation_rate", "validation_failure_rate", "conflict_observation_rate", "skill_reuse_precision"]
    lines = ["| mode | " + " | ".join(metrics) + " |", "|---" * (len(metrics) + 1) + "|"]
    for mode in sorted(grouped):
        cells = []
        for metric in metrics:
            values = grouped[mode][metric]
            cells.append(f"{mean(values):.3f} +/- {stdev(values):.3f}" if len(values) > 1 else f"{values[0]:.3f}")
        lines.append("| " + mode + " | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
