from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
from statistics import mean

from skilldecay import DecayPolicy, Skill, SkillDebtType, SkillEvent, SkillLibrary, SkillState


class RetrievalMode(str, Enum):
    NO_SKILL = "no_skill"
    STATIC = "static"
    APPEND_ONLY = "append_only"
    RECENCY = "recency"
    LRU = "lru"
    LFU = "lfu"
    VALIDATION_GATED = "validation_gated"
    HEALTH_SCORE = "health_score"
    SKILL_DECAY = "skill_decay"
    DECAY_NO_UTILITY = "decay_no_utility"
    DECAY_NO_STALENESS = "decay_no_staleness"
    DECAY_NO_CONFLICT = "decay_no_conflict"
    ORACLE = "oracle"


@dataclass(frozen=True)
class BenchmarkConfig:
    benchmark: str = "synthetic"
    seed: int = 0
    steps: int = 180
    drift_step: int = 80
    pollution_rate: float = 0.25
    task_families: tuple[str, ...] = ("nav", "search", "code", "web", "tool")
    clean_skills_per_family: int = 2
    polluted_skills_per_family: int = 3
    base_success: float = 0.40
    clean_benefit: float = 0.30
    stale_penalty: float = -0.24
    over_specific_penalty: float = -0.15
    conflicting_penalty: float = -0.20
    max_library_size: int = 8
    policy_window: int = 24
    drift_recovery_window: int = 35


@dataclass(frozen=True)
class SimTask:
    task_id: str
    step: int
    family: str
    drifted: bool
    variant: str


@dataclass
class BenchmarkResult:
    summary: dict
    records: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    final_states: dict[str, str] = field(default_factory=dict)


DECAY_MODES = {
    RetrievalMode.SKILL_DECAY,
    RetrievalMode.DECAY_NO_UTILITY,
    RetrievalMode.DECAY_NO_STALENESS,
    RetrievalMode.DECAY_NO_CONFLICT,
}


def policy_for_mode(mode: RetrievalMode, config: BenchmarkConfig) -> DecayPolicy:
    return DecayPolicy(
        window=config.policy_window,
        deprecate_after_quarantine_steps=config.policy_window * 2,
        use_utility=mode != RetrievalMode.DECAY_NO_UTILITY,
        use_staleness=mode != RetrievalMode.DECAY_NO_STALENESS,
        use_conflict=mode != RetrievalMode.DECAY_NO_CONFLICT,
    )


def run_benchmark(mode: RetrievalMode | str, config: BenchmarkConfig) -> BenchmarkResult:
    retrieval_mode = RetrievalMode(mode)
    rng = random.Random(config.seed)
    library = build_library(config)
    tasks = build_tasks(config)
    policy = policy_for_mode(retrieval_mode, config) if retrieval_mode in DECAY_MODES else DecayPolicy(window=config.policy_window)
    records: list[dict] = []
    decisions: list[dict] = []

    for task in tasks:
        skill = select_skill(library, task, retrieval_mode, config)
        effective_debt = effective_debt_type(skill, task)
        success_probability = config.base_success if skill is None else outcome_probability(effective_debt, config)
        success = rng.random() < success_probability
        harmful = skill is not None and effective_debt != SkillDebtType.CLEAN
        helpful = skill is not None and success and not harmful
        validation_passed = validation_status(skill, task, effective_debt)
        conflict_observed = skill is not None and effective_debt == SkillDebtType.CONFLICTING
        token_cost = token_cost_for(skill, effective_debt)

        if skill is not None:
            library.record(
                skill.skill_id,
                SkillEvent(
                    task_id=task.task_id,
                    step=task.step,
                    invoked=True,
                    success=success,
                    helpful=helpful,
                    validation_passed=validation_passed,
                    conflict_observed=conflict_observed,
                    task_family=task.family,
                    token_cost=token_cost,
                ),
            )

        decisions.extend(apply_maintenance(library, retrieval_mode, policy, config, task.step))
        active_count = sum(skill.state in {SkillState.ACTIVE, SkillState.SUSPECT, SkillState.REVIVED} for skill in library)
        records.append(
            {
                "benchmark": config.benchmark,
                "mode": retrieval_mode.value,
                "seed": config.seed,
                "pollution_rate": config.pollution_rate,
                "task_id": task.task_id,
                "step": task.step,
                "family": task.family,
                "variant": task.variant,
                "drifted": task.drifted,
                "skill_id": None if skill is None else skill.skill_id,
                "debt_type": effective_debt.value,
                "success": success,
                "harmful_invocation": harmful,
                "helpful_invocation": helpful,
                "validation_passed": validation_passed,
                "conflict_observed": conflict_observed,
                "token_cost": token_cost,
                "active_library_size": active_count,
            }
        )

    return BenchmarkResult(
        summary=summarize(records, decisions, retrieval_mode, config),
        records=records,
        decisions=decisions,
        final_states=library.states(),
    )


def build_tasks(config: BenchmarkConfig) -> list[SimTask]:
    tasks: list[SimTask] = []
    variants = ("standard", "rare", "shifted")
    for step in range(config.steps):
        family = config.task_families[step % len(config.task_families)]
        variant = variants[(step // len(config.task_families)) % len(variants)]
        tasks.append(SimTask(f"{config.benchmark}_{step:04d}", step, family, step >= config.drift_step, variant))
    return tasks


def build_library(config: BenchmarkConfig) -> SkillLibrary:
    library = SkillLibrary()
    skill_index = 0
    for family in config.task_families:
        for clean_index in range(config.clean_skills_per_family):
            library.add(
                Skill(
                    skill_id=f"{family}_clean_{clean_index}",
                    description=f"General robust skill for {family} tasks",
                    task_families={family},
                    debt_type=SkillDebtType.CLEAN,
                    created_step=skill_index,
                    updated_step=skill_index,
                )
            )
            skill_index += 1

        debt_cycle = [SkillDebtType.STALE, SkillDebtType.OVER_SPECIFIC, SkillDebtType.CONFLICTING]
        polluted_count = round(config.polluted_skills_per_family * config.pollution_rate / 0.25)
        polluted_count = max(0, min(config.polluted_skills_per_family * 4, polluted_count))
        for polluted_index in range(polluted_count):
            debt_type = debt_cycle[polluted_index % len(debt_cycle)]
            library.add(
                Skill(
                    skill_id=f"{family}_{debt_type.value}_{polluted_index}",
                    description=f"Potentially {debt_type.value} skill for {family} tasks",
                    task_families={family},
                    debt_type=debt_type,
                    created_step=skill_index,
                    updated_step=skill_index,
                )
            )
            skill_index += 1
    return library


def select_skill(library: SkillLibrary, task: SimTask, mode: RetrievalMode, config: BenchmarkConfig) -> Skill | None:
    if mode == RetrievalMode.NO_SKILL:
        return None
    include_quarantined = mode not in DECAY_MODES | {RetrievalMode.VALIDATION_GATED, RetrievalMode.HEALTH_SCORE}
    candidates = library.candidates(task.family, include_quarantined=include_quarantined)
    if mode == RetrievalMode.ORACLE:
        candidates = [skill for skill in candidates if effective_debt_type(skill, task) == SkillDebtType.CLEAN]
    if mode == RetrievalMode.VALIDATION_GATED:
        candidates = [skill for skill in candidates if skill.validation_failures == 0]
    if not candidates:
        return None
    if mode in {RetrievalMode.STATIC, RetrievalMode.APPEND_ONLY}:
        return candidates[task.step % len(candidates)]
    if mode == RetrievalMode.RECENCY:
        return max(candidates, key=lambda skill: skill.updated_step)
    if mode == RetrievalMode.LRU:
        return min(candidates, key=lambda skill: skill.updated_step)
    if mode == RetrievalMode.LFU:
        return min(candidates, key=lambda skill: skill.invocation_count)
    if mode == RetrievalMode.VALIDATION_GATED:
        return candidates[task.step % len(candidates)]
    if mode == RetrievalMode.HEALTH_SCORE:
        return max(candidates, key=lambda skill: health_score(skill, config.policy_window, task.step))
    if mode in DECAY_MODES:
        return max(candidates, key=lambda skill: decay_retrieval_score(skill, config.policy_window, task.step))
    if mode == RetrievalMode.ORACLE:
        return candidates[task.step % len(candidates)]
    raise ValueError(f"unsupported retrieval mode: {mode}")


def effective_debt_type(skill: Skill | None, task: SimTask) -> SkillDebtType:
    if skill is None:
        return SkillDebtType.CLEAN
    if skill.debt_type == SkillDebtType.STALE:
        return SkillDebtType.STALE if task.drifted else SkillDebtType.CLEAN
    if skill.debt_type == SkillDebtType.OVER_SPECIFIC:
        return SkillDebtType.CLEAN if task.variant == "rare" else SkillDebtType.OVER_SPECIFIC
    return skill.debt_type


def outcome_probability(debt_type: SkillDebtType, config: BenchmarkConfig) -> float:
    adjustments = {
        SkillDebtType.CLEAN: config.clean_benefit,
        SkillDebtType.STALE: config.stale_penalty,
        SkillDebtType.OVER_SPECIFIC: config.over_specific_penalty,
        SkillDebtType.CONFLICTING: config.conflicting_penalty,
    }
    return min(0.96, max(0.04, config.base_success + adjustments[debt_type]))


def validation_status(skill: Skill | None, task: SimTask, debt_type: SkillDebtType) -> bool:
    if skill is None:
        return True
    if debt_type == SkillDebtType.STALE and task.drifted:
        return False
    return True


def token_cost_for(skill: Skill | None, debt_type: SkillDebtType) -> int:
    if skill is None:
        return 45
    extra = {
        SkillDebtType.CLEAN: 65,
        SkillDebtType.STALE: 120,
        SkillDebtType.OVER_SPECIFIC: 95,
        SkillDebtType.CONFLICTING: 130,
    }
    return 45 + extra[debt_type]


def apply_maintenance(
    library: SkillLibrary,
    mode: RetrievalMode,
    policy: DecayPolicy,
    config: BenchmarkConfig,
    step: int,
) -> list[dict]:
    if mode == RetrievalMode.SKILL_DECAY:
        return [serialize_decision(decision, step, mode.value) for decision in policy.maintain(library, step)]
    if mode == RetrievalMode.VALIDATION_GATED:
        decisions = []
        for skill in library:
            if skill.validation_failures > 0 and skill.state != SkillState.QUARANTINED:
                previous = skill.state
                skill.state = SkillState.QUARANTINED
                decisions.append({
                    "step": step,
                    "mode": mode.value,
                    "skill_id": skill.skill_id,
                    "previous_state": previous.value,
                    "next_state": skill.state.value,
                    "reason": "validation failure",
                })
        return decisions
    if mode == RetrievalMode.HEALTH_SCORE:
        active_skills = sorted(
            [skill for skill in library if skill.state != SkillState.DEPRECATED],
            key=lambda skill: health_score(skill, config.policy_window, step),
            reverse=True,
        )
        decisions = []
        for skill in active_skills[config.max_library_size:]:
            if skill.state != SkillState.QUARANTINED:
                previous = skill.state
                skill.state = SkillState.QUARANTINED
                decisions.append({
                    "step": step,
                    "mode": mode.value,
                    "skill_id": skill.skill_id,
                    "previous_state": previous.value,
                    "next_state": skill.state.value,
                    "reason": "low health score outside capacity",
                })
        return decisions
    return []


def decay_retrieval_score(skill: Skill, window: int, step: int) -> float:
    state_bonus = 0.05 if skill.state == SkillState.REVIVED else 0.0
    state_penalty = 0.10 if skill.state == SkillState.SUSPECT else 0.0
    return skill.utility_score(window, step) - skill.staleness_score(window, step) - skill.conflict_score(window, step) + state_bonus - state_penalty


def health_score(skill: Skill, window: int, step: int) -> float:
    validation_penalty = min(1.0, skill.validation_failures / max(1, skill.invocation_count)) if skill.invocation_count else 0.0
    return 0.55 * skill.utility_score(window, step) - 0.25 * skill.conflict_score(window, step) - 0.20 * validation_penalty


def serialize_decision(decision, step: int, mode: str) -> dict:
    return {
        "step": step,
        "mode": mode,
        "skill_id": decision.skill_id,
        "previous_state": decision.previous_state.value,
        "next_state": decision.next_state.value,
        "utility": decision.utility,
        "staleness": decision.staleness,
        "conflict": decision.conflict,
        "reason": decision.reason,
    }


def summarize(records: list[dict], decisions: list[dict], mode: RetrievalMode, config: BenchmarkConfig) -> dict:
    invoked = [record for record in records if record["skill_id"]]
    post_drift = [record for record in records if record["drifted"]]
    recovery_records = [
        record
        for record in records
        if config.drift_step <= record["step"] < config.drift_step + config.drift_recovery_window
    ]
    return {
        "benchmark": config.benchmark,
        "mode": mode.value,
        "seed": config.seed,
        "pollution_rate": config.pollution_rate,
        "task_success": mean(record["success"] for record in records),
        "post_drift_success": mean(record["success"] for record in post_drift),
        "early_recovery_success": mean(record["success"] for record in recovery_records),
        "token_cost": mean(record["token_cost"] for record in records),
        "harmful_skill_invocation_rate": mean(record["harmful_invocation"] for record in records),
        "skill_reuse_precision": mean(record["helpful_invocation"] for record in invoked) if invoked else 0.0,
        "validation_failure_rate": mean(not record["validation_passed"] for record in records),
        "conflict_observation_rate": mean(record["conflict_observed"] for record in records),
        "final_active_library_size": records[-1]["active_library_size"],
        "maintenance_decisions": len(decisions),
    }
