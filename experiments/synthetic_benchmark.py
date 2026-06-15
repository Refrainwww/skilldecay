from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from skilldecay import DecayPolicy, Skill, SkillDebtType, SkillEvent, SkillLibrary, SkillState


@dataclass(frozen=True)
class Task:
    task_id: str
    step: int
    family: str
    drifted: bool


class RetrievalMode:
    NO_SKILL = "no_skill"
    STATIC = "static"
    APPEND_ONLY = "append_only"
    RECENCY = "recency"
    SKILL_DECAY = "skill_decay"


BASE_SUCCESS = 0.42
BENEFIT = {
    SkillDebtType.CLEAN: 0.28,
    SkillDebtType.STALE: -0.22,
    SkillDebtType.OVER_SPECIFIC: -0.14,
    SkillDebtType.CONFLICTING: -0.18,
}
TOKEN_COST = {
    SkillDebtType.CLEAN: 70,
    SkillDebtType.STALE: 110,
    SkillDebtType.OVER_SPECIFIC: 95,
    SkillDebtType.CONFLICTING: 120,
}


def build_library() -> SkillLibrary:
    library = SkillLibrary()
    specs = [
        ("clean_navigation", "General navigation procedure", {"nav"}, SkillDebtType.CLEAN),
        ("clean_search", "General search procedure", {"search"}, SkillDebtType.CLEAN),
        ("clean_code", "General coding-agent procedure", {"code"}, SkillDebtType.CLEAN),
        ("stale_api", "Old API workflow that fails after drift", {"code"}, SkillDebtType.STALE),
        ("stale_browser", "Old browser workflow that fails after drift", {"search"}, SkillDebtType.STALE),
        ("over_specific_nav", "Kitchen-only navigation shortcut", {"nav"}, SkillDebtType.OVER_SPECIFIC),
        ("over_specific_code", "Single-library coding workaround", {"code"}, SkillDebtType.OVER_SPECIFIC),
        ("conflict_nav", "Contradictory navigation ordering", {"nav"}, SkillDebtType.CONFLICTING),
        ("conflict_search", "Contradictory search ordering", {"search"}, SkillDebtType.CONFLICTING),
    ]
    for step, (skill_id, description, families, debt_type) in enumerate(specs):
        library.add(Skill(skill_id, description, families, debt_type, created_step=step, updated_step=step))
    return library


def generate_tasks(steps: int, drift_step: int) -> list[Task]:
    families = ["nav", "search", "code"]
    return [
        Task(task_id=f"task_{step:04d}", step=step, family=families[step % len(families)], drifted=step >= drift_step)
        for step in range(steps)
    ]


def select_skill(library: SkillLibrary, task: Task, mode: str) -> Skill | None:
    if mode == RetrievalMode.NO_SKILL:
        return None
    include_quarantined = mode != RetrievalMode.SKILL_DECAY
    candidates = library.candidates(task.family, include_quarantined=include_quarantined)
    if not candidates:
        return None
    if mode == RetrievalMode.RECENCY:
        return max(candidates, key=lambda skill: skill.updated_step)
    if mode == RetrievalMode.SKILL_DECAY:
        return max(
            candidates,
            key=lambda skill: (
                skill.utility_score(20, task.step)
                - skill.staleness_score(20, task.step)
                - skill.conflict_score(20, task.step),
                skill.updated_step,
            ),
        )
    return candidates[task.step % len(candidates)]


def apply_drift(skill: Skill, task: Task) -> SkillDebtType:
    if skill.debt_type == SkillDebtType.STALE and task.drifted:
        return SkillDebtType.STALE
    if skill.debt_type == SkillDebtType.STALE and not task.drifted:
        return SkillDebtType.CLEAN
    return skill.debt_type


def run_mode(mode: str, seed: int, steps: int, drift_step: int) -> dict:
    rng = random.Random(seed)
    library = build_library()
    policy = DecayPolicy(window=18, deprecate_after_quarantine_steps=24)
    tasks = generate_tasks(steps, drift_step)
    records = []
    decisions = []

    for task in tasks:
        skill = select_skill(library, task, mode)
        debt_type = SkillDebtType.CLEAN if skill is None else apply_drift(skill, task)
        probability = BASE_SUCCESS if skill is None else BASE_SUCCESS + BENEFIT[debt_type]
        probability = min(0.95, max(0.05, probability))
        success = rng.random() < probability
        harmful = skill is not None and debt_type != SkillDebtType.CLEAN
        helpful = skill is not None and success and not harmful
        validation_passed = not (skill is not None and debt_type == SkillDebtType.STALE and task.drifted)
        conflict_observed = skill is not None and debt_type == SkillDebtType.CONFLICTING
        token_cost = 45 if skill is None else 45 + TOKEN_COST[debt_type]

        if skill is not None:
            event = SkillEvent(
                task_id=task.task_id,
                step=task.step,
                invoked=True,
                success=success,
                helpful=helpful,
                validation_passed=validation_passed,
                conflict_observed=conflict_observed,
                task_family=task.family,
                token_cost=token_cost,
            )
            library.record(skill.skill_id, event)

        if mode == RetrievalMode.SKILL_DECAY:
            for decision in policy.maintain(library, task.step):
                decisions.append(decision.__dict__ | {
                    "previous_state": decision.previous_state.value,
                    "next_state": decision.next_state.value,
                    "step": task.step,
                })

        active_count = sum(skill.state in {SkillState.ACTIVE, SkillState.SUSPECT, SkillState.REVIVED} for skill in library)
        records.append({
            "task_id": task.task_id,
            "step": task.step,
            "family": task.family,
            "drifted": task.drifted,
            "skill_id": None if skill is None else skill.skill_id,
            "debt_type": debt_type.value,
            "success": success,
            "harmful_invocation": harmful,
            "helpful_invocation": helpful,
            "token_cost": token_cost,
            "active_library_size": active_count,
        })

    invoked = [record for record in records if record["skill_id"]]
    post_drift = [record for record in records if record["drifted"]]
    summary = {
        "mode": mode,
        "seed": seed,
        "task_success": mean(record["success"] for record in records),
        "post_drift_success": mean(record["success"] for record in post_drift),
        "token_cost": mean(record["token_cost"] for record in records),
        "harmful_skill_invocation_rate": mean(record["harmful_invocation"] for record in records),
        "skill_reuse_precision": mean(record["helpful_invocation"] for record in invoked) if invoked else 0.0,
        "final_active_library_size": records[-1]["active_library_size"],
        "decisions": len(decisions),
    }
    return {"summary": summary, "records": records, "decisions": decisions, "final_states": library.states()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/results.json"))
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--drift-step", type=int, default=55)
    parser.add_argument("--seeds", type=int, default=10)
    args = parser.parse_args()

    modes = [
        RetrievalMode.NO_SKILL,
        RetrievalMode.STATIC,
        RetrievalMode.APPEND_ONLY,
        RetrievalMode.RECENCY,
        RetrievalMode.SKILL_DECAY,
    ]
    runs = [
        run_mode(mode, seed, args.steps, args.drift_step)
        for seed in range(args.seeds)
        for mode in modes
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"runs": runs}, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
