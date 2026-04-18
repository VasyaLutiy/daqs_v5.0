"""
Tests for Phase 1 — typed SocialState (PLAN_2026_APR_14.md).

Covers:
  test_1.1 — SocialState is immutable: with_context() does not mutate original
  test_1.2 — with_concept() correctly adds a concept
  test_1.3 — with_trigger_exhausted() correctly marks a trigger
  test_1.4 — to_pddl_facts() produces correct PDDL facts (no duplicates, valid syntax)
  test_1.5 — from_dict() / to_dict() round-trip without data loss
  test_1.6 — to_pddl_facts() output passes validate_problem_predicates (no unknown predicates)
"""

from pathlib import Path
import sys
import re

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from npc_engine.engine.dialogue.state import SocialState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_state(**overrides) -> SocialState:
    defaults = dict(
        persona_id="player_001",
        current_context="ctx_intro",
        goal_context="ctx_core",
        concepts=frozenset(),
        visited_contexts=frozenset(["ctx_intro"]),
        unlocked_contexts=frozenset(),
        exhausted_triggers=frozenset(),
        shared_items=frozenset(),
        current_mood="",
        can_quest=True,
        oracle_path=None,
    )
    defaults.update(overrides)
    return SocialState(**defaults)


def _valid_pddl_fact(fact: str) -> bool:
    """Check PDDL fact syntax: (predicate arg1 arg2 ...)"""
    return bool(re.fullmatch(r'\(\s*[\w-]+(\s+[\w-]+)*\s*\)', fact.strip()))


# ---------------------------------------------------------------------------
# test_1.1 — immutability: with_context() does not mutate original
# ---------------------------------------------------------------------------


def test_1_1_with_context_does_not_mutate_original():
    original = _base_state()
    new_state = original.with_context("ctx_inner")

    assert original.current_context == "ctx_intro", "Original current_context must be unchanged"
    assert "ctx_inner" not in original.visited_contexts, "Original visited_contexts must be unchanged"
    assert new_state.current_context == "ctx_inner"
    assert "ctx_inner" in new_state.visited_contexts
    assert "ctx_intro" in new_state.visited_contexts  # previously visited preserved


# ---------------------------------------------------------------------------
# test_1.2 — with_concept() adds concept without touching original
# ---------------------------------------------------------------------------


def test_1_2_with_concept_adds_concept():
    original = _base_state(concepts=frozenset(["cpt_quest_easy"]))
    new_state = original.with_concept("cpt_rumor")

    assert "cpt_rumor" not in original.concepts, "Original concepts must not be modified"
    assert "cpt_rumor" in new_state.concepts
    assert "cpt_quest_easy" in new_state.concepts  # prior concept preserved


def test_1_2_with_concept_idempotent():
    """Adding the same concept twice results in exactly one entry."""
    state = _base_state().with_concept("cpt_x").with_concept("cpt_x")
    assert state.concepts == frozenset(["cpt_x"])


# ---------------------------------------------------------------------------
# test_1.3 — with_trigger_exhausted() marks trigger without mutating original
# ---------------------------------------------------------------------------


def test_1_3_with_trigger_exhausted():
    original = _base_state()
    new_state = original.with_trigger_exhausted("trig_welcome")

    assert "trig_welcome" not in original.exhausted_triggers
    assert "trig_welcome" in new_state.exhausted_triggers


# ---------------------------------------------------------------------------
# test_1.4 — to_pddl_facts() correctness
# ---------------------------------------------------------------------------


def test_1_4_to_pddl_facts_basic():
    state = _base_state(
        concepts=frozenset(["cpt_rumor", "cpt_quest_easy"]),
        visited_contexts=frozenset(["ctx_intro", "ctx_meeting"]),
        current_mood="curious",
    )
    facts = state.to_pddl_facts()

    assert isinstance(facts, list)
    assert len(facts) > 0


def test_1_4_to_pddl_facts_no_duplicates():
    state = _base_state(
        concepts=frozenset(["cpt_a", "cpt_b"]),
        visited_contexts=frozenset(["ctx_intro"]),
    )
    facts = state.to_pddl_facts()
    assert len(facts) == len(set(facts)), "to_pddl_facts() must not produce duplicate facts"


def test_1_4_to_pddl_facts_valid_syntax():
    state = _base_state(
        concepts=frozenset(["cpt_rumor"]),
        visited_contexts=frozenset(["ctx_intro", "ctx_meeting"]),
        exhausted_triggers=frozenset(["trig_coin"]),
        current_mood="curious",
    )
    for fact in state.to_pddl_facts():
        assert _valid_pddl_fact(fact), f"Invalid PDDL fact syntax: {fact!r}"


def test_1_4_to_pddl_facts_empty_concepts():
    state = _base_state()
    facts = state.to_pddl_facts()
    # Only active-context, visited facts — no has-concept lines
    has_concept_facts = [f for f in facts if "has-concept" in f]
    assert has_concept_facts == []
    active_ctx_facts = [f for f in facts if "active-context" in f]
    assert len(active_ctx_facts) == 1


def test_1_4_to_pddl_facts_contains_active_context():
    state = _base_state(current_context="ctx_meeting")
    facts = state.to_pddl_facts()
    assert any("active-context" in f and "ctx_meeting" in f for f in facts)


def test_1_4_to_pddl_facts_no_mood_when_empty():
    state = _base_state(current_mood="")
    facts = state.to_pddl_facts()
    assert not any("current-mood" in f for f in facts)


def test_1_4_to_pddl_facts_mood_present_when_set():
    state = _base_state(current_mood="hostile")
    facts = state.to_pddl_facts()
    assert any("current-mood" in f and "hostile" in f for f in facts)


# ---------------------------------------------------------------------------
# test_1.5 — from_dict() / to_dict() round-trip
# ---------------------------------------------------------------------------


def test_1_5_round_trip_basic():
    original = _base_state(
        concepts=frozenset(["cpt_a", "cpt_b"]),
        visited_contexts=frozenset(["ctx_intro", "ctx_mid"]),
        unlocked_contexts=frozenset(["ctx_secret"]),
        exhausted_triggers=frozenset(["trig_x"]),
        shared_items=frozenset(["item_coin"]),
        current_mood="curious",
        can_quest=False,
        oracle_path=("ctx_intro", "ctx_mid", "ctx_core"),
    )
    d = original.to_dict()
    restored = SocialState.from_dict(d)

    assert restored.persona_id == original.persona_id
    assert restored.current_context == original.current_context
    assert restored.goal_context == original.goal_context
    assert restored.concepts == original.concepts
    assert restored.visited_contexts == original.visited_contexts
    assert restored.unlocked_contexts == original.unlocked_contexts
    assert restored.exhausted_triggers == original.exhausted_triggers
    assert restored.shared_items == original.shared_items
    assert restored.current_mood == original.current_mood
    assert restored.can_quest == original.can_quest
    assert restored.oracle_path == original.oracle_path


def test_1_5_from_dict_accepts_legacy_target_goal_key():
    """from_dict must accept the old dict key 'target_goal' (not 'goal_context')."""
    d = {
        "persona_id": "player",
        "current_context": "ctx_intro",
        "target_goal": "ctx_end",   # legacy key
        "concepts": ["cpt_x"],
    }
    state = SocialState.from_dict(d)
    assert state.goal_context == "ctx_end"


def test_1_5_to_dict_contains_legacy_target_goal_key():
    """to_dict must emit 'target_goal' for backwards-compatible API consumers."""
    state = _base_state(goal_context="ctx_core")
    d = state.to_dict()
    assert "target_goal" in d
    assert d["target_goal"] == "ctx_core"


def test_1_5_to_dict_lists_are_sorted():
    """to_dict must return sorted lists so API output is deterministic."""
    state = _base_state(concepts=frozenset(["z_concept", "a_concept", "m_concept"]))
    d = state.to_dict()
    assert d["concepts"] == sorted(d["concepts"])


def test_1_5_round_trip_empty_oracle_path():
    state = _base_state(oracle_path=None)
    restored = SocialState.from_dict(state.to_dict())
    assert restored.oracle_path is None


# ---------------------------------------------------------------------------
# test_1.6 — to_pddl_facts() output is acceptable to validate_problem_predicates
# ---------------------------------------------------------------------------


def test_1_6_pddl_facts_valid_against_social_domain(tmp_path):
    """
    Build a minimal domain that declares all predicates used by to_pddl_facts,
    then verify validate_problem_predicates accepts them without errors.
    """
    try:
        from npc_engine.engine.master.planner_libs import validate_problem_predicates
    except Exception as exc:
        pytest.skip(f"Cannot import validate_problem_predicates: {exc}")

    # Minimal domain covering all predicates emitted by to_pddl_facts
    domain = """
    (define (domain test-social)
      (:requirements :strips)
      (:predicates
        (active-context ?player ?ctx)
        (has-concept ?player ?concept)
        (visited ?ctx)
        (unlocked ?ctx)
        (exhausted ?trigger)
        (current-mood ?player ?mood)
      )
    )
    """

    state = _base_state(
        concepts=frozenset(["cpt_rumor"]),
        visited_contexts=frozenset(["ctx_intro"]),
        unlocked_contexts=frozenset(["ctx_secret"]),
        exhausted_triggers=frozenset(["trig_welcome"]),
        current_mood="curious",
    )
    facts = state.to_pddl_facts()

    init_block = "\n".join(f"    {f}" for f in facts)
    problem = f"""
    (define (problem test-p)
      (:domain test-social)
      (:objects
        player_001 - object
        ctx_intro ctx_secret ctx_core - object
        cpt_rumor - object
        trig_welcome - object
        curious - object
      )
      (:init
{init_block}
      )
      (:goal (visited ctx_intro))
    )
    """

    error = validate_problem_predicates(domain, problem)
    assert error is None, f"validate_problem_predicates reported: {error}"
