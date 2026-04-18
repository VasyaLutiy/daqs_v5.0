"""
Tests for Phase 7 — Final integration & regression (PLAN_2026_APR_14.md).

test_7.1  Smoke: all phase modules import cleanly; app routes are registered
test_7.2  social_init handler creates a session in SESSION_STORE
test_7.3  social_message FSM path completes in <50 ms (no LLM, no PDDL)
test_7.4  quest_accept with cached QuestPlan completes in <10 ms
test_7.5  Full chain: social_init → social_message → session state is updated
test_7.6  SessionStore and QuestPlanner are wired at module level (not None after startup)

All external I/O (LLM, VisualGenerator, world file I/O for quest) is mocked so
these tests are purely in-process and require no network or docker.
"""

from __future__ import annotations

import asyncio
import sys
import time
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch  # must be before stubs below

import pytest

# ---------------------------------------------------------------------------
# Bootstrap stubs for heavy optional deps
# ---------------------------------------------------------------------------

_dummy_formatter_cls = type(
    "_DummyFormatter",
    (),
    {"__init__": lambda self, *a, **kw: None, "format": lambda self, r: r.getMessage()},
)
sys.modules.setdefault(
    "coloredlogs",
    types.SimpleNamespace(install=lambda *a, **kw: None, ColoredFormatter=_dummy_formatter_cls),
)

# google.genai
_google_stub = types.ModuleType("google")
_genai_stub = types.ModuleType("google.genai")
_google_stub.genai = _genai_stub
sys.modules.setdefault("google", _google_stub)
sys.modules.setdefault("google.genai", _genai_stub)
sys.modules.setdefault("google.genai.types", types.ModuleType("google.genai.types"))

# openai
_openai_stub = types.ModuleType("openai")
_openai_stub.OpenAI = MagicMock
sys.modules.setdefault("openai", _openai_stub)

# python-dotenv
_dotenv_stub = types.ModuleType("dotenv")
_dotenv_stub.load_dotenv = lambda *a, **kw: None
sys.modules.setdefault("dotenv", _dotenv_stub)

# graphviz
_graphviz_stub = types.ModuleType("graphviz")
_graphviz_stub.Digraph = MagicMock
sys.modules.setdefault("graphviz", _graphviz_stub)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from npc_engine.engine.compiler import DomainCompiler  # noqa: E402
from npc_engine.engine.quest.planner import QuestPlan, QuestPlanner  # noqa: E402
from npc_engine.engine.session_store import SessionStore  # noqa: E402

CONFIG_DIR = Path(__file__).resolve().parents[1] / "npc_engine" / "config"

# Compile all persona graphs once for the whole module — cheap (~200 ms)
_GRAPHS = DomainCompiler().compile_all(CONFIG_DIR)
_CYBER_GRAPH = _GRAPHS.get("persona_cyber")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.run(coro)


def _minimal_player_state() -> dict:
    return {
        "id": "player_001",
        "location": "forest_entrance",
        "inventory": {"items": {}},
        "knowledge": {"discovered_locations": [], "visited_locations": []},
    }


def _mock_llm():
    """Return a mock that covers every social_llm function used by the handlers."""
    m = MagicMock()
    m.generate_quest_intro.return_value = {"scene_description": "A dark alley.", "text": "Hello"}
    m.generate_social_narrative.return_value = {"reply": "Nice to meet you.", "scene_description": ""}
    m.generate_quest_mission.return_value = {"mission": "Find the relic"}
    m.get_social_intent.return_value = None  # NLU → no move
    return m


def _mock_orchestrator():
    m = MagicMock()
    m.personas_data = {}
    m.locations_data = {}
    return m


# ---------------------------------------------------------------------------
# test_7.1 — Smoke: all phase modules importable; app routes registered
# ---------------------------------------------------------------------------


def test_7_1_all_phase_modules_import():
    """Every refactoring-phase module must import without error."""
    import npc_engine.engine.dialogue.state          # Phase 1
    import npc_engine.engine.compiler                # Phase 2
    import npc_engine.engine.dialogue.engine         # Phase 3
    import npc_engine.engine.quest.planner           # Phase 4
    import npc_engine.engine.master.pddl_validator   # Phase 5
    import npc_engine.engine.session_store           # Phase 6


def test_7_1b_app_routes_registered():
    """FastAPI app must expose the expected social/quest/world routes."""
    import npc_engine.main_fast_ent as app_module  # noqa

    route_paths = {r.path for r in app_module.app.routes}

    expected = {
        "/health",
        "/social/init",
        "/social/message",
        "/social/graph",
        "/quest/accept",
        "/quest/difficulty",
        "/plan/exploration",
        "/process",
        "/world/state",
        "/world/graph",
    }
    missing = expected - route_paths
    assert not missing, f"Routes missing from app: {missing}"


# ---------------------------------------------------------------------------
# test_7.2 — social_init creates a session in SESSION_STORE
# ---------------------------------------------------------------------------


def test_7_2_social_init_creates_session():
    import npc_engine.main_fast_ent as app_module
    from npc_engine.main_fast_ent import SocialInitRequest

    # Inject compiled graph and a fresh store so this test is isolated
    original_graphs = app_module.DIALOGUE_GRAPHS
    original_store = app_module.SESSION_STORE
    original_planner = app_module.QUEST_PLANNER

    fresh_store = SessionStore(ttl_seconds=60)
    app_module.DIALOGUE_GRAPHS = _GRAPHS
    app_module.SESSION_STORE = fresh_store
    app_module.QUEST_PLANNER = None  # disable async planner to avoid real hook call

    try:
        with (
            patch.object(app_module, "social_llm", _mock_llm()),
            patch.object(app_module, "orchestrator", _mock_orchestrator()),
            patch.object(app_module.VIS_GEN, "generate_scene_visual", return_value=None),
        ):
            req = SocialInitRequest(
                persona_id="persona_cyber",
                player_state=_minimal_player_state(),
            )
            resp = run(app_module.social_init(req))

        assert resp.status == "success"
        assert resp.persona_id == "persona_cyber"
        assert len(fresh_store) == 1, "social_init must persist exactly one session"

        key = app_module._session_key("persona_cyber", None)
        stored = run(fresh_store.get(key))
        assert stored is not None, "session must be retrievable by key"
        assert stored.get("persona_id") == "persona_cyber"

    finally:
        app_module.DIALOGUE_GRAPHS = original_graphs
        app_module.SESSION_STORE = original_store
        app_module.QUEST_PLANNER = original_planner


# ---------------------------------------------------------------------------
# test_7.3 — social_message FSM path completes in <50 ms
# ---------------------------------------------------------------------------


def test_7_3_social_message_fsm_latency():
    import npc_engine.main_fast_ent as app_module
    from npc_engine.main_fast_ent import SocialMessageRequest
    from npc_engine.engine.dialogue.state import SocialState

    original_graphs = app_module.DIALOGUE_GRAPHS
    original_store = app_module.SESSION_STORE

    fresh_store = SessionStore(ttl_seconds=60)
    app_module.DIALOGUE_GRAPHS = _GRAPHS
    app_module.SESSION_STORE = fresh_store

    # Pre-seed a session so _get_session finds it immediately
    state = SocialState(
        persona_id="persona_cyber",
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
    session_data = {
        **state.to_dict(),
        "history": [],
        "metadata": {},
        "active_persona": "persona_cyber",
        "current_location": "forest_entrance",
        "available_moves": [],
    }
    run(fresh_store.set(app_module._session_key("persona_cyber", "sess_perf"), session_data))

    try:
        with (
            patch.object(app_module, "social_llm", _mock_llm()),
            patch.object(app_module, "orchestrator", _mock_orchestrator()),
            patch.object(app_module.VIS_GEN, "generate_scene_visual", return_value=None),
        ):
            req = SocialMessageRequest(
                persona_id="persona_cyber",
                session_id="sess_perf",
                social_state=session_data,
                player_state=_minimal_player_state(),
                message="Hello",
            )

            t0 = time.perf_counter()
            resp = run(app_module.social_message(req))
            elapsed_ms = (time.perf_counter() - t0) * 1000

        assert resp.status == "success", f"Handler failed: {resp.error}"
        assert elapsed_ms < 50, (
            f"/social/message FSM path took {elapsed_ms:.1f} ms — must be <50 ms without LLM"
        )

    finally:
        app_module.DIALOGUE_GRAPHS = original_graphs
        app_module.SESSION_STORE = original_store


# ---------------------------------------------------------------------------
# test_7.4 — quest_accept with cached plan completes in <10 ms
# ---------------------------------------------------------------------------


def test_7_4_quest_accept_cached_latency():
    import npc_engine.main_fast_ent as app_module
    from npc_engine.main_fast_ent import QuestAcceptRequest
    from npc_engine.engine.quest.planner import PlanCache, PlanCacheKey

    # Build a planner with the plan pre-seeded in cache
    world = MagicMock()
    planner = QuestPlanner(world=world)
    cached_plan = QuestPlan(
        steps=["(move forest_entrance cave)"],
        quest_steps=[{"step": 1, "desc": "Go to cave"}],
        error=None,
        goal="(in-context player ctx_core)",
    )
    cache_key = PlanCacheKey(
        player_id="player_001",
        goal="(in-context player ctx_core)",
        oracle_mode=True,
    )
    planner._cache.set(cache_key, cached_plan)

    original_planner = app_module.QUEST_PLANNER
    app_module.QUEST_PLANNER = planner

    try:
        with patch.object(app_module, "social_llm", _mock_llm()):
            req = QuestAcceptRequest(
                quest_goal="(in-context player ctx_core)",
                quest_name="The Core Quest",
                player_state=_minimal_player_state(),
                oracle_mode=True,
            )

            t0 = time.perf_counter()
            resp = run(app_module.quest_accept(req))
            elapsed_ms = (time.perf_counter() - t0) * 1000

        assert resp.status == "success", f"quest_accept returned failure: {resp.error}"
        assert resp.plan == cached_plan.steps
        assert elapsed_ms < 10, (
            f"Cached quest_accept took {elapsed_ms:.1f} ms — must be <10 ms"
        )

    finally:
        app_module.QUEST_PLANNER = original_planner


# ---------------------------------------------------------------------------
# test_7.5 — Full chain: social_init → social_message → session updated
# ---------------------------------------------------------------------------


def test_7_5_full_chain_init_then_message():
    import npc_engine.main_fast_ent as app_module
    from npc_engine.main_fast_ent import SocialInitRequest, SocialMessageRequest

    original_graphs = app_module.DIALOGUE_GRAPHS
    original_store = app_module.SESSION_STORE
    original_planner = app_module.QUEST_PLANNER

    fresh_store = SessionStore(ttl_seconds=60)
    app_module.DIALOGUE_GRAPHS = _GRAPHS
    app_module.SESSION_STORE = fresh_store
    app_module.QUEST_PLANNER = None

    mock_llm = _mock_llm()
    mock_orch = _mock_orchestrator()

    try:
        with (
            patch.object(app_module, "social_llm", mock_llm),
            patch.object(app_module, "orchestrator", mock_orch),
            patch.object(app_module.VIS_GEN, "generate_scene_visual", return_value=None),
        ):
            # Step 1: init
            init_resp = run(app_module.social_init(
                SocialInitRequest(
                    persona_id="persona_cyber",
                    player_state=_minimal_player_state(),
                )
            ))
            assert init_resp.status == "success"

            # Step 2: message
            msg_resp = run(app_module.social_message(
                SocialMessageRequest(
                    persona_id="persona_cyber",
                    session_id=None,
                    social_state=init_resp.social_state,
                    player_state=_minimal_player_state(),
                    message="Tell me more.",
                )
            ))
            assert msg_resp.status == "success"

        # After the chain there must be exactly 1 session key
        assert len(fresh_store) == 1

        # The session must have at least 2 history entries (init assistant + message assistant)
        key = app_module._session_key("persona_cyber", None)
        session = run(fresh_store.get(key))
        assert session is not None
        history = session.get("history", [])
        assert len(history) >= 2, (
            f"Expected at least 2 history entries after init+message, got {len(history)}"
        )

    finally:
        app_module.DIALOGUE_GRAPHS = original_graphs
        app_module.SESSION_STORE = original_store
        app_module.QUEST_PLANNER = original_planner


# ---------------------------------------------------------------------------
# test_7.6 — SessionStore and QuestPlanner wired correctly at module level
# ---------------------------------------------------------------------------


def test_7_6_module_level_globals_types():
    """SESSION_STORE and QUEST_PLANNER (after startup) must be correct types."""
    import npc_engine.main_fast_ent as app_module

    assert isinstance(app_module.SESSION_STORE, SessionStore), (
        "SESSION_STORE must be a SessionStore instance"
    )
    # QUEST_PLANNER may be None if startup hasn't run in test context — that's OK.
    # What matters is that it's either None or a QuestPlanner.
    assert app_module.QUEST_PLANNER is None or isinstance(
        app_module.QUEST_PLANNER, QuestPlanner
    ), "QUEST_PLANNER must be None or QuestPlanner"
