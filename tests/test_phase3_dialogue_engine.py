"""Phase 3 tests: DialogueEngine FSM

Tests cover:
  3.1  DialogueMove is hashable and stringifies to pddl_str
  3.2  get_valid_moves — shift-context for free navigation
  3.3  get_valid_moves — locked context NOT exposed as shift when player lacks key
  3.4  get_valid_moves — apply-concept emitted when player holds concept key
  3.5  get_valid_moves — apply-combo-concept when player holds both combo keys
  3.6  get_valid_moves — learn-concept from current context
  3.7  get_valid_moves — activate-trigger only when not exhausted / concept not owned
  3.8  get_valid_moves — do-behavior emitted matching current mood only
  3.9  apply_move shift-context — updates context + mood induction
  3.10 apply_move learn-concept — adds concept to frozenset
  3.11 apply_move activate-trigger — marks exhausted + adds concept
  3.12 apply_move apply-concept — unlocks + enters context
  3.13 apply_move do-behavior — state unchanged (pure narrative)
  3.14 is_goal_reached — True when current_context == goal
  3.15 is_goal_reached — True when goal_context in unlocked_contexts
  3.16 oracle BFS — returns None when goal already reached
  3.17 oracle BFS — returns first move on shortest path
  3.18 compiler — behavior_rules parsed from real paladin.yaml
  3.19 compiler — equipment_tags populated correctly
  3.20 compiler — persona_tags populated correctly
"""

import dataclasses
import sys
from pathlib import Path

import pytest

# Make sure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from npc_engine.engine.compiler import (
    CompiledBehaviorRule,
    CompiledContext,
    CompiledDialogueGraph,
    CompiledTrigger,
    DialogueTransition,
    DomainCompiler,
    TransitionCondition,
)
from npc_engine.engine.dialogue.engine import DialogueEngine, DialogueMove
from npc_engine.engine.dialogue.state import SocialState


# ---------------------------------------------------------------------------
# Fixtures — minimal compiled graph
# ---------------------------------------------------------------------------

def _make_ctx(ctx_id: str, *, is_locked=False, provides_concept=None,
              induces_mood="", is_start=False,
              transitions=()) -> CompiledContext:
    return CompiledContext(
        ctx_id=ctx_id,
        name=ctx_id,
        description="",
        is_start=is_start,
        is_locked=is_locked,
        provides_concept=provides_concept,
        induces_mood=induces_mood,
        transitions=transitions,
    )


def _make_transition(from_ctx, to_ctx, *, condition=None, direction="forward"):
    cond = condition or TransitionCondition()
    return DialogueTransition(
        from_ctx=from_ctx, to_ctx=to_ctx, condition=cond, direction=direction
    )


def _make_trigger(trigger_id, parent_ctx, yields=None) -> CompiledTrigger:
    return CompiledTrigger(
        trigger_id=trigger_id,
        name=trigger_id,
        parent_context=parent_ctx,
        yields=yields,
    )


def _make_rule(rule_id, mood="neutral", *, holding_tag=None, wearing_tag=None,
               empty_hands=False, resolved_id=None) -> CompiledBehaviorRule:
    return CompiledBehaviorRule(
        rule_id=rule_id,
        mood=mood,
        requires_holding_tag=holding_tag,
        requires_wearing_tag=wearing_tag,
        requires_empty_hands=empty_hands,
        narrative_template="does something",
        resolved_item_id=resolved_id,
    )


def _make_graph(*, contexts=None, transitions=None, triggers=None,
                behavior_rules=None, start="ctx_a") -> CompiledDialogueGraph:
    contexts = contexts or {}
    transitions = transitions or {}
    triggers = triggers or {}
    behavior_rules = behavior_rules or ()
    return CompiledDialogueGraph(
        persona_id="test_persona",
        persona_name="Test Persona",
        contexts=contexts,
        concepts=frozenset(),
        triggers=triggers,
        behavior_rules=tuple(behavior_rules),
        equipment_tags=frozenset(),
        start_context=start,
        transitions=transitions,
        persona_tags=frozenset(),
    )


def _make_state(current_context="ctx_a", goal_context="ctx_goal",
                concepts=(), unlocked_contexts=(), exhausted_triggers=(),
                current_mood="") -> SocialState:
    return SocialState(
        persona_id="test_persona",
        current_context=current_context,
        goal_context=goal_context,
        concepts=frozenset(concepts),
        visited_contexts=frozenset([current_context]),
        unlocked_contexts=frozenset(unlocked_contexts),
        exhausted_triggers=frozenset(exhausted_triggers),
        shared_items=frozenset(),
        current_mood=current_mood,
        can_quest=True,
        oracle_path=None,
    )


# ---------------------------------------------------------------------------
# 3.1 DialogueMove basics
# ---------------------------------------------------------------------------

def test_3_1_dialogue_move_is_hashable_and_str():
    m = DialogueMove(kind="shift-context", pddl_str="shift-context player ctx_a ctx_b", to_ctx="ctx_b")
    assert str(m) == "shift-context player ctx_a ctx_b"
    # hashable (can be placed in a set)
    assert m in {m}


# ---------------------------------------------------------------------------
# 3.2 get_valid_moves — free shift-context
# ---------------------------------------------------------------------------

def test_3_2_free_shift_context():
    t = _make_transition("ctx_a", "ctx_b")
    ctx_a = _make_ctx("ctx_a", transitions=(t,))
    ctx_b = _make_ctx("ctx_b")
    graph = _make_graph(
        contexts={"ctx_a": ctx_a, "ctx_b": ctx_b},
        transitions={"ctx_a": (t,)},
        start="ctx_a",
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a")
    moves = engine.get_valid_moves(state)
    kinds = {m.kind for m in moves}
    assert "shift-context" in kinds
    shift = next(m for m in moves if m.kind == "shift-context")
    assert shift.to_ctx == "ctx_b"


# ---------------------------------------------------------------------------
# 3.3 Locked context suppressed when player lacks key
# ---------------------------------------------------------------------------

def test_3_3_locked_ctx_not_exposed_without_key():
    cond = TransitionCondition(required_concept="cpt_key")
    t = _make_transition("ctx_a", "ctx_locked", condition=cond)
    ctx_a = _make_ctx("ctx_a", transitions=(t,))
    ctx_locked = _make_ctx("ctx_locked", is_locked=True)
    graph = _make_graph(
        contexts={"ctx_a": ctx_a, "ctx_locked": ctx_locked},
        transitions={"ctx_a": (t,)},
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a")  # no concepts
    moves = engine.get_valid_moves(state)
    to_locked = [m for m in moves if m.to_ctx == "ctx_locked"]
    assert not to_locked, "Should not offer locked context when player lacks key"


# ---------------------------------------------------------------------------
# 3.4 apply-concept emitted when player has key
# ---------------------------------------------------------------------------

def test_3_4_apply_concept_when_player_has_key():
    cond = TransitionCondition(required_concept="cpt_key")
    t = _make_transition("ctx_a", "ctx_locked", condition=cond)
    ctx_a = _make_ctx("ctx_a", transitions=(t,))
    ctx_locked = _make_ctx("ctx_locked", is_locked=True)
    graph = _make_graph(
        contexts={"ctx_a": ctx_a, "ctx_locked": ctx_locked},
        transitions={"ctx_a": (t,)},
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", concepts=("cpt_key",))
    moves = engine.get_valid_moves(state)
    ac_moves = [m for m in moves if m.kind == "apply-concept"]
    assert len(ac_moves) == 1
    assert ac_moves[0].concept == "cpt_key"
    assert ac_moves[0].to_ctx == "ctx_locked"


# ---------------------------------------------------------------------------
# 3.5 apply-combo-concept emitted when player holds both combo keys
# ---------------------------------------------------------------------------

def test_3_5_apply_combo_concept():
    cond = TransitionCondition(required_combo=("cpt_a", "cpt_b"))
    t = _make_transition("ctx_a", "ctx_combo", condition=cond)
    ctx_a = _make_ctx("ctx_a", transitions=(t,))
    ctx_combo = _make_ctx("ctx_combo", is_locked=True)
    graph = _make_graph(
        contexts={"ctx_a": ctx_a, "ctx_combo": ctx_combo},
        transitions={"ctx_a": (t,)},
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", concepts=("cpt_a", "cpt_b"))
    moves = engine.get_valid_moves(state)
    combo_moves = [m for m in moves if m.kind == "apply-combo-concept"]
    assert len(combo_moves) == 1
    assert combo_moves[0].combo == ("cpt_a", "cpt_b")


def test_3_5b_apply_combo_concept_suppressed_with_one_key():
    cond = TransitionCondition(required_combo=("cpt_a", "cpt_b"))
    t = _make_transition("ctx_a", "ctx_combo", condition=cond)
    ctx_a = _make_ctx("ctx_a", transitions=(t,))
    ctx_combo = _make_ctx("ctx_combo", is_locked=True)
    graph = _make_graph(
        contexts={"ctx_a": ctx_a, "ctx_combo": ctx_combo},
        transitions={"ctx_a": (t,)},
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", concepts=("cpt_a",))  # missing cpt_b
    moves = engine.get_valid_moves(state)
    assert not any(m.kind == "apply-combo-concept" for m in moves)


# ---------------------------------------------------------------------------
# 3.6 learn-concept from current context
# ---------------------------------------------------------------------------

def test_3_6_learn_concept():
    ctx_a = _make_ctx("ctx_a", provides_concept="cpt_wisdom")
    graph = _make_graph(contexts={"ctx_a": ctx_a})
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a")
    moves = engine.get_valid_moves(state)
    lc = [m for m in moves if m.kind == "learn-concept"]
    assert len(lc) == 1
    assert lc[0].concept == "cpt_wisdom"


def test_3_6b_learn_concept_suppressed_when_already_owned():
    ctx_a = _make_ctx("ctx_a", provides_concept="cpt_wisdom")
    graph = _make_graph(contexts={"ctx_a": ctx_a})
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", concepts=("cpt_wisdom",))
    moves = engine.get_valid_moves(state)
    assert not any(m.kind == "learn-concept" for m in moves)


# ---------------------------------------------------------------------------
# 3.7 activate-trigger
# ---------------------------------------------------------------------------

def test_3_7_activate_trigger_emitted():
    trig = _make_trigger("trig_1", "ctx_a", yields="cpt_secret")
    graph = _make_graph(
        contexts={"ctx_a": _make_ctx("ctx_a")},
        triggers={"trig_1": trig},
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a")
    moves = engine.get_valid_moves(state)
    at = [m for m in moves if m.kind == "activate-trigger"]
    assert len(at) == 1
    assert at[0].trigger_id == "trig_1"
    assert at[0].concept == "cpt_secret"


def test_3_7b_trigger_suppressed_when_exhausted():
    trig = _make_trigger("trig_1", "ctx_a", yields="cpt_secret")
    graph = _make_graph(
        contexts={"ctx_a": _make_ctx("ctx_a")},
        triggers={"trig_1": trig},
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", exhausted_triggers=("trig_1",))
    moves = engine.get_valid_moves(state)
    assert not any(m.kind == "activate-trigger" for m in moves)


def test_3_7c_trigger_suppressed_when_concept_already_owned():
    trig = _make_trigger("trig_1", "ctx_a", yields="cpt_secret")
    graph = _make_graph(
        contexts={"ctx_a": _make_ctx("ctx_a")},
        triggers={"trig_1": trig},
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", concepts=("cpt_secret",))
    moves = engine.get_valid_moves(state)
    assert not any(m.kind == "activate-trigger" for m in moves)


# ---------------------------------------------------------------------------
# 3.8 do-behavior — mood-gated
# ---------------------------------------------------------------------------

def test_3_8_do_behavior_matches_mood():
    rule = _make_rule("act_salute", mood="neutral", holding_tag="holy", resolved_id="item_sword")
    graph = _make_graph(
        contexts={"ctx_a": _make_ctx("ctx_a")},
        behavior_rules=[rule],
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", current_mood="neutral")
    moves = engine.get_valid_moves(state)
    beh = [m for m in moves if m.kind == "do-behavior"]
    assert len(beh) == 1
    assert beh[0].rule_id == "act_salute"
    assert "item_sword" in beh[0].pddl_str


def test_3_8b_do_behavior_suppressed_wrong_mood():
    rule = _make_rule("act_salute", mood="angry")
    graph = _make_graph(
        contexts={"ctx_a": _make_ctx("ctx_a")},
        behavior_rules=[rule],
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", current_mood="neutral")
    moves = engine.get_valid_moves(state)
    assert not any(m.kind == "do-behavior" for m in moves)


def test_3_8c_do_behavior_suppressed_when_no_mood():
    rule = _make_rule("act_salute", mood="neutral")
    graph = _make_graph(
        contexts={"ctx_a": _make_ctx("ctx_a")},
        behavior_rules=[rule],
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", current_mood="")  # no mood
    moves = engine.get_valid_moves(state)
    assert not any(m.kind == "do-behavior" for m in moves)


# ---------------------------------------------------------------------------
# 3.9 apply_move — shift-context induces mood
# ---------------------------------------------------------------------------

def test_3_9_apply_shift_context_updates_state_and_mood():
    t = _make_transition("ctx_a", "ctx_b")
    ctx_b = _make_ctx("ctx_b", induces_mood="resolute")
    graph = _make_graph(
        contexts={"ctx_a": _make_ctx("ctx_a", transitions=(t,)), "ctx_b": ctx_b},
        transitions={"ctx_a": (t,)},
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a")
    move = DialogueMove(kind="shift-context", pddl_str="shift-context player ctx_a ctx_b", to_ctx="ctx_b")
    new_state = engine.apply_move(move, state)

    assert new_state.current_context == "ctx_b"
    assert "ctx_b" in new_state.visited_contexts
    assert new_state.current_mood == "resolute"
    # Original state untouched
    assert state.current_context == "ctx_a"
    assert state.current_mood == ""


# ---------------------------------------------------------------------------
# 3.10 apply_move — learn-concept
# ---------------------------------------------------------------------------

def test_3_10_apply_learn_concept():
    graph = _make_graph(contexts={"ctx_a": _make_ctx("ctx_a")})
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a")
    move = DialogueMove(kind="learn-concept", pddl_str="learn-concept player ctx_a cpt_x", concept="cpt_x")
    new_state = engine.apply_move(move, state)
    assert "cpt_x" in new_state.concepts
    assert "cpt_x" not in state.concepts  # immutability


# ---------------------------------------------------------------------------
# 3.11 apply_move — activate-trigger
# ---------------------------------------------------------------------------

def test_3_11_apply_activate_trigger():
    graph = _make_graph(contexts={"ctx_a": _make_ctx("ctx_a")})
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a")
    move = DialogueMove(
        kind="activate-trigger",
        pddl_str="activate-trigger player ctx_a trig_1 cpt_secret",
        trigger_id="trig_1",
        concept="cpt_secret",
    )
    new_state = engine.apply_move(move, state)
    assert "trig_1" in new_state.exhausted_triggers
    assert "cpt_secret" in new_state.concepts


# ---------------------------------------------------------------------------
# 3.12 apply_move — apply-concept unlocks + enters + mood
# ---------------------------------------------------------------------------

def test_3_12_apply_concept_unlocks_and_enters():
    ctx_locked = _make_ctx("ctx_locked", is_locked=True, induces_mood="holy")
    graph = _make_graph(
        contexts={"ctx_a": _make_ctx("ctx_a"), "ctx_locked": ctx_locked},
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", concepts=("cpt_key",))
    move = DialogueMove(
        kind="apply-concept",
        pddl_str="apply-concept player ctx_a ctx_locked cpt_key",
        to_ctx="ctx_locked",
        concept="cpt_key",
    )
    new_state = engine.apply_move(move, state)
    assert "ctx_locked" in new_state.unlocked_contexts
    assert new_state.current_context == "ctx_locked"
    assert new_state.current_mood == "holy"


# ---------------------------------------------------------------------------
# 3.13 apply_move — do-behavior is pure narrative
# ---------------------------------------------------------------------------

def test_3_13_do_behavior_no_state_change():
    graph = _make_graph(contexts={"ctx_a": _make_ctx("ctx_a")})
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", current_mood="neutral")
    move = DialogueMove(kind="do-behavior", pddl_str="do_act_salute player", rule_id="act_salute")
    new_state = engine.apply_move(move, state)
    assert new_state == state


# ---------------------------------------------------------------------------
# 3.14 / 3.15 is_goal_reached
# ---------------------------------------------------------------------------

def test_3_14_goal_reached_by_current_context():
    graph = _make_graph(contexts={"ctx_goal": _make_ctx("ctx_goal")})
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_goal", goal_context="ctx_goal")
    assert engine.is_goal_reached(state)


def test_3_15_goal_reached_by_unlocked():
    graph = _make_graph(contexts={"ctx_a": _make_ctx("ctx_a")})
    engine = DialogueEngine(graph)
    state = _make_state(
        current_context="ctx_a",
        goal_context="ctx_goal",
        unlocked_contexts=("ctx_goal",),
    )
    assert engine.is_goal_reached(state)


def test_3_15b_goal_not_reached():
    graph = _make_graph(contexts={"ctx_a": _make_ctx("ctx_a")})
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", goal_context="ctx_goal")
    assert not engine.is_goal_reached(state)


# ---------------------------------------------------------------------------
# 3.16 oracle — None when goal already reached
# ---------------------------------------------------------------------------

def test_3_16_oracle_none_when_goal_reached():
    graph = _make_graph(contexts={"ctx_a": _make_ctx("ctx_a")})
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", goal_context="ctx_a")
    assert engine.get_oracle_next_step(state) is None


# ---------------------------------------------------------------------------
# 3.17 oracle BFS — finds shortest path
# ---------------------------------------------------------------------------

def test_3_17_oracle_bfs_finds_first_move():
    # Graph: ctx_a → ctx_b → ctx_goal
    t_ab = _make_transition("ctx_a", "ctx_b")
    t_bg = _make_transition("ctx_b", "ctx_goal")
    ctx_a = _make_ctx("ctx_a", transitions=(t_ab,))
    ctx_b = _make_ctx("ctx_b", transitions=(t_bg,))
    ctx_goal = _make_ctx("ctx_goal")
    graph = _make_graph(
        contexts={"ctx_a": ctx_a, "ctx_b": ctx_b, "ctx_goal": ctx_goal},
        transitions={"ctx_a": (t_ab,), "ctx_b": (t_bg,)},
        start="ctx_a",
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", goal_context="ctx_goal")
    hint = engine.get_oracle_next_step(state)
    assert hint is not None
    assert hint.kind == "shift-context"
    assert hint.to_ctx == "ctx_b"


def test_3_17b_oracle_returns_none_when_unreachable():
    # No path from ctx_a to ctx_goal
    graph = _make_graph(
        contexts={"ctx_a": _make_ctx("ctx_a"), "ctx_goal": _make_ctx("ctx_goal")},
        transitions={},
        start="ctx_a",
    )
    engine = DialogueEngine(graph)
    state = _make_state(current_context="ctx_a", goal_context="ctx_goal")
    assert engine.get_oracle_next_step(state) is None


# ---------------------------------------------------------------------------
# 3.18-3.20 Integration: real paladin.yaml parsed via DomainCompiler
# ---------------------------------------------------------------------------

PALADIN_YAML = PROJECT_ROOT / "npc_engine" / "config" / "social_world" / "nodes" / "personas" / "paladin.yaml"


@pytest.mark.skipif(not PALADIN_YAML.exists(), reason="paladin.yaml not found")
def test_3_18_behavior_rules_parsed_from_real_yaml():
    compiler = DomainCompiler()
    graphs = compiler.compile_persona_file(PALADIN_YAML)
    aric = next((g for g in graphs if g.persona_id == "persona_sir_aric"), None)
    assert aric is not None, "persona_sir_aric not found in paladin.yaml"
    assert len(aric.behavior_rules) > 0, "Expected at least one behavior rule"
    rule_ids = {r.rule_id for r in aric.behavior_rules}
    assert "act_holy_salute" in rule_ids


@pytest.mark.skipif(not PALADIN_YAML.exists(), reason="paladin.yaml not found")
def test_3_19_equipment_tags_populated():
    compiler = DomainCompiler()
    graphs = compiler.compile_persona_file(PALADIN_YAML)
    aric = next((g for g in graphs if g.persona_id == "persona_sir_aric"), None)
    assert aric is not None
    # paladin.yaml has tags: blade, holy, radiant, armor, heavy, helmet
    assert "holy" in aric.equipment_tags
    assert "armor" in aric.equipment_tags


@pytest.mark.skipif(not PALADIN_YAML.exists(), reason="paladin.yaml not found")
def test_3_20_persona_tags_populated():
    compiler = DomainCompiler()
    graphs = compiler.compile_persona_file(PALADIN_YAML)
    aric = next((g for g in graphs if g.persona_id == "persona_sir_aric"), None)
    assert aric is not None
    assert "paladin" in aric.persona_tags
    assert "lawful" in aric.persona_tags
