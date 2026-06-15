from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from statistics import mean
from typing import Iterable


class SkillState(str, Enum):
    ACTIVE = "active"
    SUSPECT = "suspect"
    QUARANTINED = "quarantined"
    DEPRECATED = "deprecated"
    REVIVED = "revived"


class SkillDebtType(str, Enum):
    CLEAN = "clean"
    STALE = "stale"
    OVER_SPECIFIC = "over_specific"
    CONFLICTING = "conflicting"


@dataclass(frozen=True)
class SkillEvent:
    task_id: str
    step: int
    invoked: bool
    success: bool
    helpful: bool
    validation_passed: bool = True
    conflict_observed: bool = False
    task_family: str = "default"
    token_cost: int = 0


@dataclass
class Skill:
    skill_id: str
    description: str
    task_families: set[str]
    debt_type: SkillDebtType = SkillDebtType.CLEAN
    state: SkillState = SkillState.ACTIVE
    created_step: int = 0
    updated_step: int = 0
    invocation_count: int = 0
    success_count: int = 0
    helpful_count: int = 0
    validation_failures: int = 0
    conflict_count: int = 0
    quarantined_at: int | None = None
    history: list[SkillEvent] = field(default_factory=list)

    def record(self, event: SkillEvent) -> None:
        self.history.append(event)
        self.updated_step = event.step
        if not event.invoked:
            return
        self.invocation_count += 1
        self.success_count += int(event.success)
        self.helpful_count += int(event.helpful)
        self.validation_failures += int(not event.validation_passed)
        self.conflict_count += int(event.conflict_observed)

    def recent_events(self, window: int, current_step: int) -> list[SkillEvent]:
        earliest = max(0, current_step - window + 1)
        return [event for event in self.history if event.step >= earliest]

    def utility_score(self, window: int, current_step: int) -> float:
        events = [event for event in self.recent_events(window, current_step) if event.invoked]
        if not events:
            return 0.5
        return mean(0.7 * event.success + 0.3 * event.helpful for event in events)

    def staleness_score(self, window: int, current_step: int) -> float:
        events = [event for event in self.recent_events(window, current_step) if event.invoked]
        if not events:
            age = current_step - self.updated_step
            return min(1.0, age / max(1, window * 2))
        validation_failure_rate = mean(not event.validation_passed for event in events)
        recent_failure_rate = mean(not event.success for event in events)
        age_pressure = min(1.0, (current_step - self.created_step) / max(1, window * 4))
        return min(1.0, 0.45 * validation_failure_rate + 0.35 * recent_failure_rate + 0.20 * age_pressure)

    def conflict_score(self, window: int, current_step: int) -> float:
        events = [event for event in self.recent_events(window, current_step) if event.invoked]
        if not events:
            return 0.0
        return mean(event.conflict_observed for event in events)

    def matches(self, task_family: str) -> bool:
        return task_family in self.task_families or "*" in self.task_families


@dataclass
class SkillLibrary:
    skills: dict[str, Skill] = field(default_factory=dict)

    def add(self, skill: Skill) -> None:
        self.skills[skill.skill_id] = skill

    def record(self, skill_id: str, event: SkillEvent) -> None:
        self.skills[skill_id].record(event)

    def candidates(self, task_family: str, include_quarantined: bool = False) -> list[Skill]:
        blocked = {SkillState.DEPRECATED}
        if not include_quarantined:
            blocked.add(SkillState.QUARANTINED)
        return [
            skill
            for skill in self.skills.values()
            if skill.state not in blocked and skill.matches(task_family)
        ]

    def states(self) -> dict[str, str]:
        return {skill_id: skill.state.value for skill_id, skill in self.skills.items()}

    def __iter__(self) -> Iterable[Skill]:
        return iter(self.skills.values())
