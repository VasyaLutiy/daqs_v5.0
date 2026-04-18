"""
Tests for Phase 0 fixes (PLAN_2026_APR_14.md).

Covers:
  test_0.1 — SocialInitRequest has no duplicate player_state field
  test_0.2 — problem.pddl.j2 references domain narrative-flow-v2
  test_0.3 — pddl_orchestrator.get_domain("social") uses social_domain_v2 directly
  test_0.7 — build_social_init_facts does not mutate objects when mood is already known
"""

import logging
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: stub heavy optional deps so imports don't crash in unit tests
# ---------------------------------------------------------------------------

_dummy_formatter_cls = type(
    "_DummyFormatter",
    (),
    {
        "__init__": lambda self, *a, **kw: None,
        "format": lambda self, r: r.getMessage(),
    },
)

sys.modules.setdefault(
    "coloredlogs",
    types.SimpleNamespace(
        install=lambda *a, **kw: None,
        ColoredFormatter=_dummy_formatter_cls,
    ),
)

# Stub google.genai so main_fast_ent.py can be imported without the SDK installed
_google_stub = types.ModuleType("google")
_genai_stub = types.ModuleType("google.genai")
_google_stub.genai = _genai_stub
sys.modules.setdefault("google", _google_stub)
sys.modules.setdefault("google.genai", _genai_stub)
sys.modules.setdefault("google.genai.types", types.ModuleType("google.genai.types"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# test_0.1 — SocialInitRequest has no duplicate player_state field
# ---------------------------------------------------------------------------


def test_0_1_social_init_request_no_duplicate_player_state():
    """SocialInitRequest must have exactly one player_state field in source."""
    source = (PROJECT_ROOT / "npc_engine" / "main_fast_ent.py").read_text()
    # Locate the SocialInitRequest class block
    lines = source.splitlines()
    in_class = False
    class_lines = []
    for line in lines:
        if "class SocialInitRequest" in line:
            in_class = True
        elif in_class and line.startswith("class "):
            break
        if in_class:
            class_lines.append(line)

    assert class_lines, "SocialInitRequest class not found in main_fast_ent.py"

    # Count annotation lines for player_state inside the class
    player_state_defs = [
        l for l in class_lines
        if "player_state" in l and (":" in l) and "def " not in l and "#" not in l.lstrip()
    ]
    assert len(player_state_defs) == 1, (
        f"Expected exactly 1 player_state field definition, "
        f"found {len(player_state_defs)}: {player_state_defs}"
    )


# ---------------------------------------------------------------------------
# test_0.2 — problem.pddl.j2 uses narrative-flow-v2
# ---------------------------------------------------------------------------


def test_0_2_problem_template_domain_name():
    """problem.pddl.j2 must reference (:domain narrative-flow) — Phase 5 renamed v2→clean."""
    template_path = PROJECT_ROOT / "npc_engine" / "config" / "logic" / "social" / "problem.pddl.j2"
    assert template_path.exists(), f"Template not found: {template_path}"
    content = template_path.read_text()
    assert "(:domain narrative-flow)" in content, (
        "problem.pddl.j2 must declare (:domain narrative-flow) but got:\n"
        + next(l for l in content.splitlines() if ":domain" in l)
    )
    assert "narrative-flow-v2" not in content, (
        "v2 suffix must be gone after Phase 5 rename"
    )


# ---------------------------------------------------------------------------
# test_0.3 — get_domain("social") loads social_domain_v2 directly (no V4 attempt)
# ---------------------------------------------------------------------------


def test_0_3_get_domain_no_v4_fallback(tmp_path):
    """get_domain('social') loads social_domain.pddl.j2 directly — no V4 fallback."""
    try:
        import jinja2
        from npc_engine.engine.master.pddl_orchestrator import PDDLOrchestrator
        from npc_engine.engine.master.pddl_builder import PDDLTemplateRenderer
    except ImportError as exc:
        pytest.skip(f"dependency not available: {exc}")

    # Create a tmp dir with only the canonical social_domain.pddl.j2 (Phase 5 name)
    logic_dir = tmp_path / "logic"
    logic_dir.mkdir()
    social_world_dir = tmp_path / "social_world"
    social_world_dir.mkdir()
    (social_world_dir / "social_domain.pddl.j2").write_text(
        "(define (domain narrative-flow) (:requirements :adl) (:predicates))"
    )

    orch = PDDLOrchestrator(logic_dir=str(logic_dir))
    orch.renderer = PDDLTemplateRenderer([logic_dir, social_world_dir])

    # V4 template must not exist
    assert not (social_world_dir / "social_unified_v4.pddl.j2").exists()

    result = orch.get_domain("social")
    assert "narrative-flow" in result, f"Expected narrative-flow domain, got: {result!r}"
    assert "narrative-flow-v2" not in result, "v2 suffix must be gone after Phase 5"


# ---------------------------------------------------------------------------
# test_0.7 — build_social_init_facts behaviour with known vs unknown moods
# ---------------------------------------------------------------------------


def _make_assembler():
    """Build a SocialWorldAssembler with a stub logger and a dummy config_path."""
    try:
        from npc_engine.engine.master.pddl_libs import SocialWorldAssembler
    except Exception as exc:
        return None, str(exc)
    assembler = SocialWorldAssembler(
        config_path=Path("/nonexistent"),
        logger=MagicMock(),
    )
    return assembler, None


def test_0_7_known_mood_does_not_mutate_objects():
    """
    When current_mood is already in domain_moods, objects list must not be
    mutated — confirming the guard condition works correctly.
    """
    assembler, err = _make_assembler()
    if assembler is None:
        pytest.skip(f"Cannot import SocialWorldAssembler: {err}")

    domain_moods = {"curious"}
    objects: list[str] = ["ctx_intro - context"]
    original_len = len(objects)

    assembler.build_social_init_facts(
        player_id="player_001",
        goal_context_id="ctx_core",
        contexts={},
        triggers={},
        dynamic_state={"current_mood": "curious"},
        target_persona_data=None,
        active_persona=None,
        domain_moods=domain_moods,
        objects=objects,
    )

    assert len(objects) == original_len, (
        "objects list must NOT be extended when mood is already in domain_moods"
    )


def test_0_7_unknown_mood_appends_to_objects():
    """
    When current_mood is NOT in domain_moods, exactly one entry must be appended
    to objects so the :objects section stays consistent with :init facts.
    """
    assembler, err = _make_assembler()
    if assembler is None:
        pytest.skip(f"Cannot import SocialWorldAssembler: {err}")

    domain_moods: set[str] = set()
    objects: list[str] = ["ctx_intro - context"]

    facts = assembler.build_social_init_facts(
        player_id="player_001",
        goal_context_id="ctx_core",
        contexts={},
        triggers={},
        dynamic_state={"current_mood": "angry"},
        target_persona_data=None,
        active_persona=None,
        domain_moods=domain_moods,
        objects=objects,
    )

    mood_entries = [o for o in objects if "angry" in o]
    assert len(mood_entries) == 1, (
        f"Expected exactly 1 mood entry appended for unknown mood, got: {mood_entries}"
    )
    assert any("current-mood" in f for f in facts), (
        "init_facts must contain (current-mood ...) predicate"
    )
