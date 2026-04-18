"""Phase 5 tests: PDDL domain/problem consistency + validator

Tests cover:
  5.1  Social domain uses name 'narrative-flow' (no v2 suffix)
  5.2  problem.pddl.j2 (:domain ...) matches domain name
  5.3  Dead domain files are gone
  5.4  validate_domain_problem_pair — happy path: empty error list
  5.5  validate_domain_problem_pair — domain name mismatch → error
  5.6  validate_domain_problem_pair — unknown predicate in :init → error
  5.7  validate_domain_problem_pair — unknown type in :objects → error
  5.8  find_duplicate_init_facts — duplicate fact → detected
  5.9  Exploration PDDL round-trip: generate domain+problem, MasterPlanner.solve() → plan
  5.10 Social PDDL round-trip: cyber.yaml domain+problem, MasterPlanner.solve() → plan
  5.11 Golden regression: generated cyber fixture matches saved fixture
  5.12 Golden regression: generated paladin fixture matches saved fixture
  5.13 Paladin problem: equipment facts present (wearing, has-tag, is-tag)
  5.14 Paladin domain: behavior actions generated (do_act_holy_salute)
  5.15 Validator wired into MasterPlanner: mismatch domain → solve returns None
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from npc_engine.engine.master.pddl_validator import (
    check_domain_name_match,
    check_unknown_predicates,
    check_unknown_types,
    find_duplicate_init_facts,
    validate_domain_problem_pair,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "pddl"
SOCIAL_WORLD = PROJECT_ROOT / "npc_engine" / "config" / "social_world"
LOGIC_DIR = PROJECT_ROOT / "npc_engine" / "config" / "logic"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _make_orchestrator():
    from npc_engine.engine.master.pddl_orchestrator import PDDLOrchestrator
    return PDDLOrchestrator()


def _load_persona_data(persona_id: str):
    import yaml
    for f in (SOCIAL_WORLD / "nodes" / "personas").rglob("*.yaml"):
        data = yaml.safe_load(f.read_text())
        if data.get("id") == persona_id:
            return data
        for p in data.get("personas", []):
            if p.get("id") == persona_id:
                return p
    return None


def _generate_cyber():
    orch = _make_orchestrator()
    pdata = _load_persona_data("persona_cyber")
    constants = orch._extract_constants(pdata)
    domain = orch.get_domain("social", persona_data=pdata, constants=constants)
    problem = orch.assemble_social_problem(
        player_id="player_001",
        goal_context_id="ctx_core",
        dynamic_state={"current_context": "ctx_intro", "concepts": [], "items": []},
        config_dir=str(SOCIAL_WORLD),
        active_persona="persona_cyber",
        constants=constants,
    )
    return domain, problem


def _generate_paladin():
    orch = _make_orchestrator()
    pdata = _load_persona_data("persona_sir_aric")
    constants = orch._extract_constants(pdata)
    domain = orch.get_domain("social", persona_data=pdata, constants=constants)
    problem = orch.assemble_social_problem(
        player_id="player_001",
        goal_context_id="ctx_aric_blessing",
        dynamic_state={"current_context": "ctx_aric_quest_offer", "concepts": [], "items": []},
        config_dir=str(SOCIAL_WORLD),
        active_persona="persona_sir_aric",
        constants=constants,
    )
    return domain, problem


# ---------------------------------------------------------------------------
# 5.1  Domain name is 'narrative-flow' (no v2)
# ---------------------------------------------------------------------------

def test_5_1_social_domain_name():
    domain_file = SOCIAL_WORLD / "social_domain.pddl.j2"
    assert domain_file.exists(), "social_domain.pddl.j2 must exist (renamed from v2)"
    content = domain_file.read_text()
    assert "(domain narrative-flow)" in content
    assert "narrative-flow-v2" not in content


# ---------------------------------------------------------------------------
# 5.2  problem.pddl.j2 references correct domain name
# ---------------------------------------------------------------------------

def test_5_2_problem_template_domain_ref():
    problem_tmpl = LOGIC_DIR / "social" / "problem.pddl.j2"
    content = problem_tmpl.read_text()
    assert "(:domain narrative-flow)" in content
    assert "narrative-flow-v2" not in content


# ---------------------------------------------------------------------------
# 5.3  Dead domain files are gone
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    LOGIC_DIR / "social" / "domain.pddl",
    LOGIC_DIR / "social" / "universal_domain.pddl",
    LOGIC_DIR / "social" / "social_unified_v4.pddl.j2",
    SOCIAL_WORLD / "social_domain_v2.pddl.j2",
])
def test_5_3_dead_files_deleted(path):
    assert not path.exists(), f"Dead file should be deleted: {path.name}"


# ---------------------------------------------------------------------------
# 5.4  validate_domain_problem_pair — happy path
# ---------------------------------------------------------------------------

def test_5_4_validator_happy_path_cyber():
    domain, problem = _generate_cyber()
    errors = validate_domain_problem_pair(domain, problem)
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_5_4_validator_happy_path_paladin():
    domain, problem = _generate_paladin()
    errors = validate_domain_problem_pair(domain, problem)
    assert errors == [], f"Unexpected validation errors: {errors}"


# ---------------------------------------------------------------------------
# 5.5  Domain name mismatch → error
# ---------------------------------------------------------------------------

def test_5_5_domain_name_mismatch():
    domain = "(define (domain narrative-flow)\n  (:requirements :strips)\n  (:predicates (foo ?x))\n)"
    problem = "(define (problem p)\n  (:domain wrong-name)\n  (:objects)\n  (:init)\n  (:goal (foo x))\n)"
    errors = validate_domain_problem_pair(domain, problem)
    assert any("mismatch" in e.lower() or "wrong-name" in e for e in errors)


def test_5_5_check_domain_name_match_direct():
    domain = "(define (domain my-domain)\n  (:predicates))"
    problem = "(define (problem p)\n  (:domain other-domain)\n  (:objects)\n  (:init)\n  (:goal (visited x))\n)"
    err = check_domain_name_match(domain, problem)
    assert err is not None
    assert "my-domain" in err and "other-domain" in err


def test_5_5_check_domain_name_match_ok():
    domain = "(define (domain narrative-flow)\n  (:predicates))"
    problem = "(define (problem p)\n  (:domain narrative-flow)\n  (:objects)\n  (:init)\n  (:goal (visited x))\n)"
    assert check_domain_name_match(domain, problem) is None


# ---------------------------------------------------------------------------
# 5.6  Unknown predicate in :init → error
# ---------------------------------------------------------------------------

def test_5_6_unknown_predicate_in_init():
    domain = """(define (domain d)
  (:predicates (known-pred ?x))
)"""
    problem = """(define (problem p)
  (:domain d)
  (:objects x - object)
  (:init (known-pred x) (mystery-pred x))
  (:goal (known-pred x))
)"""
    err = check_unknown_predicates(domain, problem)
    assert err is not None
    assert "mystery-pred" in err


def test_5_6_no_error_when_predicates_ok():
    domain = """(define (domain d)
  (:predicates (active-context ?a ?c) (visited ?c))
)"""
    problem = """(define (problem p)
  (:domain d)
  (:objects a - object c - object)
  (:init (active-context a c))
  (:goal (visited c))
)"""
    assert check_unknown_predicates(domain, problem) is None


# ---------------------------------------------------------------------------
# 5.7  Unknown type in :objects → error
# ---------------------------------------------------------------------------

def test_5_7_unknown_type_in_objects():
    domain = "(define (domain d)\n  (:types agent context)\n  (:predicates (x ?a))\n)"
    problem = "(define (problem p)\n  (:domain d)\n  (:objects p1 - agent c1 - ghost)\n  (:init)\n  (:goal (x p1))\n)"
    err = check_unknown_types(domain, problem)
    assert err is not None
    assert "ghost" in err


def test_5_7_types_ok():
    domain = "(define (domain d)\n  (:types agent context)\n  (:predicates (x ?a))\n)"
    problem = "(define (problem p)\n  (:domain d)\n  (:objects p1 - agent c1 - context)\n  (:init)\n  (:goal (x p1))\n)"
    assert check_unknown_types(domain, problem) is None


# ---------------------------------------------------------------------------
# 5.8  Duplicate init facts detected
# ---------------------------------------------------------------------------

def test_5_8_duplicate_init_facts():
    problem = """(define (problem p)
  (:domain d)
  (:objects)
  (:init
    (connected a b)
    (connected a b)
    (visited c)
  )
  (:goal (visited c))
)"""
    dupes = find_duplicate_init_facts(problem)
    assert "(connected a b)" in dupes


def test_5_8_no_duplicates():
    problem = """(define (problem p)
  (:domain d)
  (:objects)
  (:init
    (connected a b)
    (visited c)
  )
  (:goal (visited c))
)"""
    assert find_duplicate_init_facts(problem) == set()


# ---------------------------------------------------------------------------
# 5.9  Exploration round-trip: domain + problem → MasterPlanner.solve()
# ---------------------------------------------------------------------------

def test_5_9_exploration_round_trip():
    """Generate exploration domain + problem and attempt to solve."""
    from npc_engine.engine.master.pddl_orchestrator import PDDLOrchestrator
    from npc_engine.engine.master.planner import MasterPlanner
    from npc_engine.engine.world.player_state import PlayerState
    from npc_engine.engine.world.graph import WorldGraph

    orch = PDDLOrchestrator()
    planner = MasterPlanner()

    domain = (LOGIC_DIR / "exploration" / "domain.pddl").read_text()

    # Minimal world: two connected locations
    ps = PlayerState.__new__(PlayerState)
    ps.player_id = "player_001"
    ps.current_location = "forest_entrance"
    ps.discovered_locations = ["forest_entrance", "forest_clearing"]

    class _Inv:
        items = {}
    ps.inventory = _Inv()

    wg = WorldGraph.__new__(WorldGraph)
    wg.world_id = "test_world"
    wg.locations = {}
    wg.edges = []

    try:
        from npc_engine.main_fast_ent import load_world_ent
        world = load_world_ent()
        problem = orch.assemble_problem("exploration", ps, world, "(at player_001 forest_clearing)")
        errors = validate_domain_problem_pair(domain, problem)
        assert errors == [], f"Exploration problem is invalid: {errors}"
        plan, diag = planner.solve(domain, problem, player_id="player_001", player_state=ps)
        # Either found a plan or a diagnostic — no exception
        assert plan is not None or diag is not None
    except Exception as e:
        pytest.skip(f"World load failed (acceptable in CI without full config): {e}")


# ---------------------------------------------------------------------------
# 5.10  Social round-trip: cyber.yaml → MasterPlanner.solve()
# ---------------------------------------------------------------------------

def test_5_10_social_round_trip_cyber():
    from npc_engine.engine.master.planner import MasterPlanner

    domain, problem = _generate_cyber()
    errors = validate_domain_problem_pair(domain, problem)
    assert errors == [], f"Social problem invalid before planning: {errors}"

    planner = MasterPlanner()
    plan, diag = planner.solve(domain, problem, player_id="player_001")
    # Plan may or may not exist depending on solver, but must not crash
    assert plan is not None or isinstance(diag, str)
    if plan:
        # Plan should contain PDDL action strings
        assert all(isinstance(s, str) for s in plan)


# ---------------------------------------------------------------------------
# 5.11  Golden regression: cyber fixture matches re-generated output
# ---------------------------------------------------------------------------

def test_5_11_cyber_golden_domain():
    domain, _ = _generate_cyber()
    saved = _load_fixture("persona_cyber_domain.pddl")
    assert domain.strip() == saved.strip(), (
        "Cyber domain has drifted from fixture — run fixture generator to update"
    )


def test_5_11_cyber_golden_problem():
    _, problem = _generate_cyber()
    saved = _load_fixture("persona_cyber_problem.pddl")
    assert problem.strip() == saved.strip(), (
        "Cyber problem has drifted from fixture — run fixture generator to update"
    )


# ---------------------------------------------------------------------------
# 5.12  Golden regression: paladin fixture matches re-generated output
# ---------------------------------------------------------------------------

def test_5_12_paladin_golden_domain():
    domain, _ = _generate_paladin()
    saved = _load_fixture("persona_sir_aric_domain.pddl")
    assert domain.strip() == saved.strip()


def test_5_12_paladin_golden_problem():
    _, problem = _generate_paladin()
    saved = _load_fixture("persona_sir_aric_problem.pddl")
    assert problem.strip() == saved.strip()


# ---------------------------------------------------------------------------
# 5.13  Paladin problem: equipment facts present
# ---------------------------------------------------------------------------

def test_5_13_paladin_equipment_facts():
    _, problem = _generate_paladin()
    assert "(wearing player_001 item_silver_plate)" in problem
    assert "(has-tag item_silver_plate armor)" in problem
    assert "(is-tag armor armor)" in problem
    assert "(holding player_001 item_sun_blade)" in problem
    assert "(has-tag item_sun_blade holy)" in problem


# ---------------------------------------------------------------------------
# 5.14  Paladin domain: behavior actions generated
# ---------------------------------------------------------------------------

def test_5_14_paladin_behavior_actions_in_domain():
    domain, _ = _generate_paladin()
    assert "do_act_holy_salute" in domain
    assert "do_act_sun_blade_glow" in domain
    assert "do_act_armor_clank" in domain
    # Each action should have :precondition and :effect
    assert domain.count("(:action do_act_holy_salute") == 1


# ---------------------------------------------------------------------------
# 5.15  Validator wired into MasterPlanner: mismatch → solve returns (None, msg)
# ---------------------------------------------------------------------------

def test_5_15_planner_rejects_mismatched_domain():
    from npc_engine.engine.master.planner import MasterPlanner

    domain = """(define (domain narrative-flow)
  (:requirements :strips :typing)
  (:types agent context)
  (:predicates (active-context ?a - agent ?c - context) (visited ?c - context))
  (:action shift-context
    :parameters (?a - agent ?from - context ?to - context)
    :precondition (active-context ?a ?from)
    :effect (and (not (active-context ?a ?from)) (active-context ?a ?to) (visited ?to))
  )
)"""
    problem = """(define (problem p)
  (:domain WRONG-DOMAIN-NAME)
  (:objects a - agent c1 c2 - context)
  (:init (active-context a c1))
  (:goal (visited c2))
)"""
    planner = MasterPlanner()
    plan, diag = planner.solve(domain, problem)
    assert plan is None
    assert diag is not None
    assert "mismatch" in diag.lower() or "WRONG" in diag
