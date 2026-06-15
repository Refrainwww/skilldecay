from __future__ import annotations

from dataclasses import dataclass

from .core import Skill, SkillLibrary, SkillState


@dataclass(frozen=True)
class MaintenanceDecision:
    skill_id: str
    previous_state: SkillState
    next_state: SkillState
    utility: float
    staleness: float
    conflict: float
    reason: str


@dataclass
class DecayPolicy:
    window: int = 20
    suspect_utility_threshold: float = 0.45
    quarantine_utility_threshold: float = 0.35
    stale_threshold: float = 0.55
    conflict_threshold: float = 0.30
    revive_utility_threshold: float = 0.70
    deprecate_after_quarantine_steps: int = 30
    use_utility: bool = True
    use_staleness: bool = True
    use_conflict: bool = True

    def maintain(self, library: SkillLibrary, current_step: int) -> list[MaintenanceDecision]:
        decisions: list[MaintenanceDecision] = []
        for skill in library:
            if skill.invocation_count == 0:
                continue
            decision = self._decide(skill, current_step)
            if decision.previous_state != decision.next_state:
                skill.state = decision.next_state
                if decision.next_state == SkillState.QUARANTINED:
                    skill.quarantined_at = current_step
                decisions.append(decision)
        return decisions

    def _decide(self, skill: Skill, current_step: int) -> MaintenanceDecision:
        raw_utility = skill.utility_score(self.window, current_step)
        raw_staleness = skill.staleness_score(self.window, current_step)
        raw_conflict = skill.conflict_score(self.window, current_step)
        utility = raw_utility if self.use_utility else 1.0
        staleness = raw_staleness if self.use_staleness else 0.0
        conflict = raw_conflict if self.use_conflict else 0.0
        previous = skill.state
        next_state = previous
        reason = "stable"

        if previous == SkillState.DEPRECATED:
            return self._decision(skill, previous, previous, utility, staleness, conflict, reason)

        if previous == SkillState.QUARANTINED:
            quarantine_age = current_step - (skill.quarantined_at or current_step)
            if utility >= self.revive_utility_threshold and staleness < self.stale_threshold and conflict < self.conflict_threshold:
                next_state = SkillState.REVIVED
                reason = "recent evidence supports revival"
            elif quarantine_age >= self.deprecate_after_quarantine_steps:
                next_state = SkillState.DEPRECATED
                reason = "quarantine expired without recovery"
            return self._decision(skill, previous, next_state, utility, staleness, conflict, reason)

        if conflict >= self.conflict_threshold:
            next_state = SkillState.QUARANTINED
            reason = "high conflict with other skills"
        elif staleness >= self.stale_threshold:
            next_state = SkillState.QUARANTINED
            reason = "validation or environment staleness"
        elif utility <= self.quarantine_utility_threshold:
            next_state = SkillState.QUARANTINED
            reason = "harmful or low-utility reuse"
        elif utility <= self.suspect_utility_threshold:
            next_state = SkillState.SUSPECT
            reason = "weak recent utility"
        elif previous in {SkillState.SUSPECT, SkillState.REVIVED} and utility > self.suspect_utility_threshold:
            next_state = SkillState.ACTIVE
            reason = "utility recovered"

        return self._decision(skill, previous, next_state, utility, staleness, conflict, reason)

    def _decision(
        self,
        skill: Skill,
        previous: SkillState,
        next_state: SkillState,
        utility: float,
        staleness: float,
        conflict: float,
        reason: str,
    ) -> MaintenanceDecision:
        return MaintenanceDecision(
            skill_id=skill.skill_id,
            previous_state=previous,
            next_state=next_state,
            utility=round(utility, 3),
            staleness=round(staleness, 3),
            conflict=round(conflict, 3),
            reason=reason,
        )
