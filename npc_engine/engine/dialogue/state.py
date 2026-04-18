"""Immutable typed social state for the dialogue subsystem.

SocialState replaces the ``Dict[str, Any]`` social_state that was threaded
through every endpoint and helper. It is frozen so that every transition
produces a new object — mutations are impossible and state history is trivially
auditable.

Serialisation contract
----------------------
``from_dict`` / ``to_dict`` provide lossless round-trips with the existing
API dict format so callers can migrate incrementally field-by-field.

PDDL export
-----------
``to_pddl_facts`` emits the planning-relevant subset of the state as
PDDL init-facts for oracle and quest planning. Physical-world state
(current_location, player inventory, …) comes from PlayerState and is NOT
duplicated here.
"""
from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True)
class SocialState:
    """Immutable snapshot of a player's social interaction state.

    Fields that are NOT here (history, metadata, current_location,
    active_persona, available_moves) belong to the session layer and are
    kept in the SessionStore side-car dict to avoid bloating the planning
    state.
    """

    persona_id: str
    current_context: str
    goal_context: str                        # was "target_goal" in dict format
    concepts: frozenset[str]
    visited_contexts: frozenset[str]
    unlocked_contexts: frozenset[str]
    exhausted_triggers: frozenset[str]
    shared_items: frozenset[str]
    current_mood: str                        # empty string = no mood set
    can_quest: bool
    oracle_path: tuple[str, ...] | None      # pre-computed PDDL plan (nullable)

    # ------------------------------------------------------------------
    # Transition helpers — each returns a NEW SocialState
    # ------------------------------------------------------------------

    def with_context(self, ctx_id: str) -> "SocialState":
        """Move to ctx_id and record it as visited."""
        return dataclasses.replace(
            self,
            current_context=ctx_id,
            visited_contexts=self.visited_contexts | {ctx_id},
        )

    def with_concept(self, concept_id: str) -> "SocialState":
        """Grant a concept to the player."""
        return dataclasses.replace(self, concepts=self.concepts | {concept_id})

    def with_context_unlocked(self, ctx_id: str) -> "SocialState":
        """Mark a context as unlocked (apply-concept effect)."""
        return dataclasses.replace(
            self, unlocked_contexts=self.unlocked_contexts | {ctx_id}
        )

    def with_trigger_exhausted(self, trigger_id: str) -> "SocialState":
        """Mark a trigger as used so it cannot fire again."""
        return dataclasses.replace(
            self, exhausted_triggers=self.exhausted_triggers | {trigger_id}
        )

    def with_item_shared(self, item_id: str) -> "SocialState":
        """Record that an item was shared with the NPC."""
        return dataclasses.replace(
            self, shared_items=self.shared_items | {item_id}
        )

    def with_oracle_path(self, path: tuple[str, ...] | None) -> "SocialState":
        """Attach (or clear) a pre-computed PDDL oracle path."""
        return dataclasses.replace(self, oracle_path=path)

    def with_goal(self, goal_ctx: str) -> "SocialState":
        """Update the goal context (e.g. after difficulty analysis)."""
        return dataclasses.replace(self, goal_context=goal_ctx)

    def with_mood(self, mood: str) -> "SocialState":
        """Set the current mood (triggered by context entry)."""
        return dataclasses.replace(self, current_mood=mood)

    # ------------------------------------------------------------------
    # PDDL export — planning-relevant facts only
    # ------------------------------------------------------------------

    def to_pddl_facts(self) -> list[str]:
        """Return PDDL init-facts for oracle / quest planning.

        Only state that the social PDDL domain cares about is included.
        Deduplication is guaranteed by frozenset membership.
        """
        player = self.persona_id
        facts: list[str] = [f"(active-context {player} {self.current_context})"]

        for c in sorted(self.concepts):
            facts.append(f"(has-concept {player} {c})")

        for ctx in sorted(self.visited_contexts):
            facts.append(f"(visited {ctx})")

        for ctx in sorted(self.unlocked_contexts):
            facts.append(f"(unlocked {ctx})")

        for t in sorted(self.exhausted_triggers):
            facts.append(f"(exhausted {t})")

        if self.current_mood:
            facts.append(f"(current-mood {player} {self.current_mood})")

        return facts

    # ------------------------------------------------------------------
    # Serialisation — backwards-compatible with dict API format
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SocialState":
        """Create SocialState from the legacy dict format.

        Unknown keys are silently ignored so the migration can happen
        incrementally — existing session dicts keep working.
        """
        return cls(
            persona_id=d.get("persona_id", ""),
            current_context=d.get("current_context", "ctx_intro"),
            goal_context=d.get("target_goal", d.get("goal_context", "ctx_core")),
            concepts=frozenset(d.get("concepts", [])),
            visited_contexts=frozenset(d.get("visited_contexts", [])),
            unlocked_contexts=frozenset(d.get("unlocked_contexts", [])),
            exhausted_triggers=frozenset(d.get("exhausted_triggers", [])),
            shared_items=frozenset(d.get("shared_items", [])),
            current_mood=d.get("current_mood", ""),
            can_quest=bool(d.get("can_quest", True)),
            oracle_path=tuple(d["oracle_path"]) if d.get("oracle_path") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the legacy dict format for API responses.

        Lists (not frozensets) are used so the result is JSON-serialisable
        without custom encoders. Keys match the existing API contract.
        """
        return {
            "persona_id": self.persona_id,
            "current_context": self.current_context,
            "target_goal": self.goal_context,      # legacy key name
            "goal_context": self.goal_context,
            "concepts": sorted(self.concepts),
            "visited_contexts": sorted(self.visited_contexts),
            "unlocked_contexts": sorted(self.unlocked_contexts),
            "exhausted_triggers": sorted(self.exhausted_triggers),
            "shared_items": sorted(self.shared_items),
            "current_mood": self.current_mood,
            "can_quest": self.can_quest,
            "oracle_path": list(self.oracle_path) if self.oracle_path else None,
        }
