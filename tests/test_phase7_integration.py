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
import json
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


async def _asgi_json_request(app, method: str, path: str, payload: dict | None = None):
    request_body = b""
    headers = [(b"host", b"testserver")]
    if payload is not None:
        request_body = json.dumps(payload).encode("utf-8")
        headers.extend(
            [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(request_body)).encode("ascii")),
            ]
        )

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    receive_messages = [{"type": "http.request", "body": request_body, "more_body": False}]
    response_status = None
    response_body_chunks = []

    async def receive():
        if receive_messages:
            return receive_messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal response_status
        if message["type"] == "http.response.start":
            response_status = message["status"]
        elif message["type"] == "http.response.body":
            response_body_chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    raw_body = b"".join(response_body_chunks)
    parsed = json.loads(raw_body.decode("utf-8")) if raw_body else None
    return response_status, parsed


def asgi_json_request(app, method: str, path: str, payload: dict | None = None):
    return run(_asgi_json_request(app, method, path, payload))


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
        "/game/sessions",
        "/game/sessions/{game_session_id}",
        "/game/sessions/{game_session_id}/world",
        "/game/sessions/{game_session_id}/world/move",
        "/game/sessions/{game_session_id}/world/pickup",
        "/game/sessions/{game_session_id}/quests/preview",
        "/game/sessions/{game_session_id}/quests/accept",
        "/game/sessions/{game_session_id}/social/init",
        "/game/sessions/{game_session_id}/social/message",
        "/game/sessions/{game_session_id}/social/exit",
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
        assert resp.session_id
        assert len(fresh_store) == 1, "social_init must persist exactly one session"
        assert resp.debug is None, "default social_init payload should be clean"
        assert "metadata" not in resp.social_state
        assert "available_moves" not in resp.social_state

        key = app_module._session_key("persona_cyber", resp.session_id)
        stored = run(fresh_store.get(key))
        assert stored is not None, "session must be retrievable by key"
        assert stored.get("persona_id") == "persona_cyber"
        assert stored.get("session_id") == resp.session_id

    finally:
        app_module.DIALOGUE_GRAPHS = original_graphs
        app_module.SESSION_STORE = original_store
        app_module.QUEST_PLANNER = original_planner


def test_7_2b_social_init_debug_payload_opt_in():
    import npc_engine.main_fast_ent as app_module
    from npc_engine.main_fast_ent import SocialInitRequest

    original_graphs = app_module.DIALOGUE_GRAPHS
    original_store = app_module.SESSION_STORE

    fresh_store = SessionStore(ttl_seconds=60)
    app_module.DIALOGUE_GRAPHS = _GRAPHS
    app_module.SESSION_STORE = fresh_store

    try:
        with (
            patch.object(app_module, "social_llm", _mock_llm()),
            patch.object(app_module, "orchestrator", _mock_orchestrator()),
            patch.object(app_module.VIS_GEN, "generate_scene_visual", return_value=None),
        ):
            resp = run(app_module.social_init(
                SocialInitRequest(
                    persona_id="persona_cyber",
                    player_state=_minimal_player_state(),
                    debug=True,
                )
            ))

        assert resp.status == "success"
        assert resp.debug is not None
        assert "persona_metadata" in resp.debug
        assert "available_moves" in resp.debug
        assert "metadata" in resp.social_state
        assert "available_moves" in resp.social_state

    finally:
        app_module.DIALOGUE_GRAPHS = original_graphs
        app_module.SESSION_STORE = original_store


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
        current_location="forest_entrance",
        inventory_signature=(),
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
            assert init_resp.session_id

            # Step 2: message
            msg_resp = run(app_module.social_message(
                SocialMessageRequest(
                    persona_id="persona_cyber",
                    session_id=init_resp.session_id,
                    social_state=init_resp.social_state,
                    player_state=_minimal_player_state(),
                    message="Tell me more.",
                )
            ))
            assert msg_resp.status == "success"
            assert msg_resp.session_id == init_resp.session_id
            assert msg_resp.debug is None
            assert "metadata" not in msg_resp.social_state
            assert "available_moves" not in msg_resp.social_state

        # After the chain there must be exactly 1 session key
        assert len(fresh_store) == 1

        # The session must have at least 2 history entries (init assistant + message assistant)
        key = app_module._session_key("persona_cyber", init_resp.session_id)
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


def test_7_7_game_session_create_and_restore():
    import npc_engine.main_fast_ent as app_module

    original_store = app_module.GAME_SESSION_STORE
    fresh_store = SessionStore(ttl_seconds=60)
    app_module.GAME_SESSION_STORE = fresh_store

    try:
        created = run(app_module.create_game_session())
        assert created.status == "success"
        assert created.game_session_id
        assert created.player_snapshot["location"] == "forest_entrance"
        assert created.world_snapshot["location"]["id"] == "forest_entrance"

        restored = run(app_module.get_game_session(created.game_session_id))
        assert restored.status == "success"
        assert restored.game_session_id == created.game_session_id
        assert restored.player_snapshot["id"] == created.player_snapshot["id"]
    finally:
        app_module.GAME_SESSION_STORE = original_store


def test_7_8_game_session_move_and_pickup():
    import npc_engine.main_fast_ent as app_module
    from npc_engine.main_fast_ent import WorldMoveRequest, WorldPickupRequest

    original_store = app_module.GAME_SESSION_STORE
    fresh_store = SessionStore(ttl_seconds=60)
    app_module.GAME_SESSION_STORE = fresh_store

    try:
        created = run(app_module.create_game_session())
        moved = run(app_module.move_game_world(
            created.game_session_id,
            WorldMoveRequest(target_location_id="forest_clearing"),
        ))
        assert moved.player_snapshot["location"] == "forest_clearing"
        assert moved.world_snapshot["location"]["id"] == "forest_clearing"

        picked = run(app_module.pickup_game_item(
            created.game_session_id,
            WorldPickupRequest(item_id="forest_herbs"),
        ))
        assert picked.player_snapshot["inventory"]["items"]["forest_herbs"] == 1
        item_ids = {item["id"] for item in picked.world_snapshot["items_nearby"]}
        assert "forest_herbs" not in item_ids
    finally:
        app_module.GAME_SESSION_STORE = original_store


def test_7_9_game_session_social_flow():
    import npc_engine.main_fast_ent as app_module
    from npc_engine.main_fast_ent import GameSocialInitRequest, GameSocialMessageRequest, GameSocialExitRequest

    original_graphs = app_module.DIALOGUE_GRAPHS
    original_social_store = app_module.SESSION_STORE
    original_game_store = app_module.GAME_SESSION_STORE

    app_module.DIALOGUE_GRAPHS = _GRAPHS
    app_module.SESSION_STORE = SessionStore(ttl_seconds=60)
    app_module.GAME_SESSION_STORE = SessionStore(ttl_seconds=60)

    try:
        with (
            patch.object(app_module, "social_llm", _mock_llm()),
            patch.object(app_module, "orchestrator", _mock_orchestrator()),
            patch.object(app_module.VIS_GEN, "generate_scene_visual", return_value=None),
        ):
            created = run(app_module.create_game_session())
            social_init = run(app_module.init_game_social(
                created.game_session_id,
                GameSocialInitRequest(persona_id="persona_cyber", can_quest=True),
            ))
            active_social = social_init.active_social_session
            assert active_social is not None
            assert social_init.ui_context["mode"] == "social"

            social_msg = run(app_module.message_game_social(
                created.game_session_id,
                GameSocialMessageRequest(
                    social_session_id=active_social["social_session_id"],
                    message="Hello there.",
                ),
            ))
            assert social_msg.active_social_session is not None
            assert len(social_msg.active_social_session["history"]) >= 2

            exited = run(app_module.exit_game_social(
                created.game_session_id,
                GameSocialExitRequest(
                    social_session_id=active_social["social_session_id"],
                ),
            ))
            assert exited.active_social_session is None
            assert exited.ui_context["mode"] == "world"
    finally:
        app_module.DIALOGUE_GRAPHS = original_graphs
        app_module.SESSION_STORE = original_social_store
        app_module.GAME_SESSION_STORE = original_game_store


def test_7_10_quest_journal_persists_in_session_snapshot():
    import npc_engine.main_fast_ent as app_module
    from npc_engine.main_fast_ent import GameQuestRequest, WorldMoveRequest

    original_game_store = app_module.GAME_SESSION_STORE
    original_planner = app_module.QUEST_PLANNER
    app_module.GAME_SESSION_STORE = SessionStore(ttl_seconds=60)
    planner_mock = MagicMock()
    planner_mock.plan_quest = AsyncMock(return_value=QuestPlan(
        steps=["(move forest_clearing hidden_grove)", "(pickup cpt_heat_potion)"],
        quest_steps=[{"step": 1, "desc": "Move to hidden grove"}, {"step": 2, "desc": "Pick up potion"}],
        error=None,
        goal="(has-item player_001 cpt_heat_potion)",
    ))
    app_module.QUEST_PLANNER = planner_mock

    try:
        created = run(app_module.create_game_session())
        restored = run(app_module.get_game_session(created.game_session_id))
        quest = restored.world_snapshot["available_quests"][0]
        mock_preview = app_module.QuestAcceptResponse(
            status="success",
            plan=["(move forest_entrance forest_clearing)", "(pickup forest_herbs)"],
            quest=[{"step": 1, "desc": "Reach the clearing"}, {"step": 2, "desc": "Collect herbs"}],
            payload={"mission": "Collect herbs from the clearing."},
        )

        with patch.object(app_module, "quest_accept", AsyncMock(return_value=mock_preview)):
            preview = run(app_module.preview_game_quest(
                created.game_session_id,
                GameQuestRequest(
                    quest_goal=quest["goal"],
                    quest_name=quest["name"],
                    oracle_mode=True,
                ),
            ))
            assert preview.quest_journal["entries"], "Quest preview should create a journal entry"
            assert preview.quest_journal["entries"][0]["status"] == "previewed"

            accepted = run(app_module.accept_game_quest(
                created.game_session_id,
                GameQuestRequest(
                    quest_goal=quest["goal"],
                    quest_name=quest["name"],
                    oracle_mode=True,
                ),
            ))
            assert accepted.active_quest is not None
            assert accepted.quest_journal["entries"][0]["status"] == "active"

            moved = run(app_module.move_game_world(
                created.game_session_id,
                WorldMoveRequest(target_location_id="forest_clearing"),
            ))

        persisted = run(app_module.get_game_session(created.game_session_id))
        history_types = {event["type"] for event in persisted.quest_journal["history"]}
        assert {"previewed", "accepted", "travel", "replanned"} <= history_types
        assert persisted.quest_journal["entries"][0]["status"] == "active"
        assert persisted.quest_journal["entries"][0]["plan"] == [
            "(move forest_clearing hidden_grove)",
            "(pickup cpt_heat_potion)",
        ]
        assert persisted.active_quest["plan"] == [
            "(move forest_clearing hidden_grove)",
            "(pickup cpt_heat_potion)",
        ]
        assert moved.quest_journal == persisted.quest_journal
    finally:
        app_module.GAME_SESSION_STORE = original_game_store
        app_module.QUEST_PLANNER = original_planner


def test_7_11_http_smoke_multi_session_isolation():
    import npc_engine.main_fast_ent as app_module

    original_graphs = app_module.DIALOGUE_GRAPHS
    original_social_store = app_module.SESSION_STORE
    original_game_store = app_module.GAME_SESSION_STORE

    app_module.DIALOGUE_GRAPHS = _GRAPHS
    app_module.SESSION_STORE = SessionStore(ttl_seconds=60)
    app_module.GAME_SESSION_STORE = SessionStore(ttl_seconds=60)

    try:
        with (
            patch.object(app_module, "social_llm", _mock_llm()),
            patch.object(app_module, "orchestrator", _mock_orchestrator()),
            patch.object(app_module.VIS_GEN, "generate_scene_visual", return_value=None),
        ):
            first_status, first = asgi_json_request(app_module.app, "POST", "/game/sessions")
            second_status, second = asgi_json_request(app_module.app, "POST", "/game/sessions")
            assert first_status == 200
            assert second_status == 200

            first_id = first["game_session_id"]
            second_id = second["game_session_id"]

            move_status, _ = asgi_json_request(
                app_module.app,
                "POST",
                f"/game/sessions/{first_id}/world/move",
                {"target_location_id": "forest_clearing"},
            )
            assert move_status == 200

            pickup_status, _ = asgi_json_request(
                app_module.app,
                "POST",
                f"/game/sessions/{first_id}/world/pickup",
                {"item_id": "forest_herbs"},
            )
            assert pickup_status == 200

            social_init_status, social_payload = asgi_json_request(
                app_module.app,
                "POST",
                f"/game/sessions/{first_id}/social/init",
                {"persona_id": "persona_cyber", "can_quest": True},
            )
            assert social_init_status == 200
            social_session_id = social_payload["active_social_session"]["social_session_id"]

            social_message_status, _ = asgi_json_request(
                app_module.app,
                "POST",
                f"/game/sessions/{first_id}/social/message",
                {"social_session_id": social_session_id, "message": "Hello"},
            )
            assert social_message_status == 200

            isolated_status, isolated_payload = asgi_json_request(
                app_module.app,
                "GET",
                f"/game/sessions/{second_id}",
            )
            assert isolated_status == 200
            assert isolated_payload["player_snapshot"]["location"] == "forest_entrance"
            assert isolated_payload["active_social_session"] is None
            assert isolated_payload["player_snapshot"]["inventory"]["items"] == {}
            assert isolated_payload["quest_journal"]["entries"] == []
            assert isolated_payload["quest_journal"]["history"] == []
    finally:
        app_module.DIALOGUE_GRAPHS = original_graphs
        app_module.SESSION_STORE = original_social_store
        app_module.GAME_SESSION_STORE = original_game_store


def test_7_12_replan_failure_keeps_action_and_clears_plan():
    import npc_engine.main_fast_ent as app_module
    from npc_engine.main_fast_ent import GameQuestRequest, WorldMoveRequest

    original_game_store = app_module.GAME_SESSION_STORE
    original_planner = app_module.QUEST_PLANNER
    app_module.GAME_SESSION_STORE = SessionStore(ttl_seconds=60)
    planner_mock = MagicMock()
    planner_mock.plan_quest = AsyncMock(return_value=QuestPlan(
        steps=[],
        quest_steps=[],
        error="planner failed to find route",
        goal="(has-item player_001 cpt_heat_potion)",
    ))
    app_module.QUEST_PLANNER = planner_mock

    try:
        created = run(app_module.create_game_session())
        restored = run(app_module.get_game_session(created.game_session_id))
        quest = restored.world_snapshot["available_quests"][0]
        mock_preview = app_module.QuestAcceptResponse(
            status="success",
            plan=["(move forest_entrance forest_clearing)", "(pickup forest_herbs)"],
            quest=[{"step": 1, "desc": "Reach the clearing"}, {"step": 2, "desc": "Collect herbs"}],
            payload={"mission": "Collect herbs from the clearing."},
        )

        with patch.object(app_module, "quest_accept", AsyncMock(return_value=mock_preview)):
            accepted = run(app_module.accept_game_quest(
                created.game_session_id,
                GameQuestRequest(
                    quest_goal=quest["goal"],
                    quest_name=quest["name"],
                    oracle_mode=True,
                ),
            ))
            assert accepted.active_quest is not None

            moved = run(app_module.move_game_world(
                created.game_session_id,
                WorldMoveRequest(target_location_id="forest_clearing"),
            ))

        assert moved.player_snapshot["location"] == "forest_clearing"
        assert moved.active_quest["plan"] == []
        assert moved.active_quest["quest_steps"] == []
        history_types = [event["type"] for event in moved.quest_journal["history"]]
        assert "travel" in history_types
        assert "replan-failed" in history_types
        assert moved.quest_journal["entries"][0]["plan"] == []
        assert moved.quest_journal["entries"][0]["status"] == "active"
    finally:
        app_module.GAME_SESSION_STORE = original_game_store
        app_module.QUEST_PLANNER = original_planner
