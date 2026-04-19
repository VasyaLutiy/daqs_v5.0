"""
Enterprise FastAPI entrypoint: API-first planning/service layer.
Keeps all planning/world logic server-side; clients call HTTP endpoints.
"""

import asyncio
import functools
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from npc_engine.bootstrap import init_logging
from npc_engine.engine.logging_config import logging_manager
from npc_engine.engine.world.graph import WorldGraph
from npc_engine.engine.world.player_state import PlayerState
from npc_engine.engine.master.pddl_orchestrator import PDDLOrchestrator
from npc_engine.engine.master.hooks.registry import execute_hook
import npc_engine.engine.master.hooks.quest_hooks  # ensure hooks registered
from npc_engine.version import __version__
from npc_engine.engine.dialogue.state import SocialState
from npc_engine.engine.dialogue.engine import DialogueEngine, DialogueMove
from npc_engine.engine.compiler import DomainCompiler, CompiledDialogueGraph
from npc_engine.engine.quest.planner import QuestPlanner, QuestPlan
from npc_engine.engine.session_store import SessionStore
from npc_engine.fastapi_ent_libs import (
    load_world,
    load_player_from_json_data,
    collect_location_data,
    collect_available_quests,
    generate_plan_and_quest,
    process_request as process_request_lib,
)

from gamemaster import social_llm
from gamemaster.prompt_orchestrator import orchestrator
from gamemaster.visual_generator import VisualGenerator
from gamemaster.engine_core import GameEngine

init_logging()
logger = logging_manager.get_component_logger("master")

BASE_DIR = Path(__file__).resolve().parent
WORLD_CONFIG_PATH = BASE_DIR / "config" / "world"
CONFIG_DIR = BASE_DIR / "config"

SESSION_STORE = SessionStore(ttl_seconds=3600.0, max_sessions=10_000)
GAME_ENGINE = GameEngine(CONFIG_DIR)
VIS_GEN = VisualGenerator()

# Compiled dialogue graphs — populated at startup by DomainCompiler
DIALOGUE_GRAPHS: Dict[str, CompiledDialogueGraph] = {}

# Async quest planner singleton — populated at startup
QUEST_PLANNER: Optional[QuestPlanner] = None


async def _startup_compile_domains() -> None:
    """Compile all persona YAMLs and initialise QuestPlanner at startup."""
    global DIALOGUE_GRAPHS, QUEST_PLANNER
    try:
        compiler = DomainCompiler()
        DIALOGUE_GRAPHS = compiler.compile_all(CONFIG_DIR)
        logger.info(
            f"[startup] DomainCompiler: loaded {len(DIALOGUE_GRAPHS)} persona(s): "
            f"{sorted(DIALOGUE_GRAPHS)}"
        )
    except Exception as exc:
        logger.error(f"[startup] DomainCompiler failed: {exc}", exc_info=True)

    try:
        world = load_world_ent()
        QUEST_PLANNER = QuestPlanner(world)
        logger.info("[startup] QuestPlanner initialised")
    except Exception as exc:
        logger.error(f"[startup] QuestPlanner init failed: {exc}", exc_info=True)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    await _startup_compile_domains()
    yield


app = FastAPI(
    title="NPC Engine API (Enterprise)",
    version=__version__,
    lifespan=_lifespan,
)


def _get_dialogue_engine(persona_id: str) -> DialogueEngine | None:
    """Return a DialogueEngine for persona_id if compiled, else None."""
    graph = DIALOGUE_GRAPHS.get(persona_id)
    return DialogueEngine(graph) if graph else None


# === Schemas ===
class PlayerStatePayload(BaseModel):
    data: Dict[str, Any]
    goal: Optional[str] = None
    oracle_mode: bool = False


class PlanRequest(BaseModel):
    input_json: Dict[str, Any]
    oracle_mode: bool = False


class PlanResponse(BaseModel):
    status: str
    metadata: Dict[str, Any]
    plan: List[str] = []
    quest: List[Dict[str, Any]] = []
    error: Optional[str] = None
    oracle_used: bool = False


class QuestDifficultyRequest(BaseModel):
    goal: Optional[str] = None


class QuestDifficultyResponse(BaseModel):
    status: str
    concept: str
    plan_length: int = 0
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    up_available: bool
    personas_loaded: int = 0
    persona_ids: List[str] = Field(default_factory=list)


class SocialInitRequest(BaseModel):
    persona_id: str = Field(..., description="Persona identifier")
    active_context: Optional[str] = None
    target_goal: Optional[str] = None
    can_quest: bool = True
    player_state: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    debug: bool = False


class SocialInitResponse(BaseModel):
    status: str
    session_id: str
    persona_id: str
    start_context: str
    target_goal: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    social_state: Dict[str, Any] = Field(default_factory=dict)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    reply: Optional[Any] = None
    image_path: Optional[str] = None
    request_id: Optional[str] = None
    duration_ms: Optional[float] = None
    can_quest: bool = True
    debug: Optional[Dict[str, Any]] = None


class SocialMessageRequest(BaseModel):
    persona_id: str
    social_state: Dict[str, Any] = Field(default_factory=dict)
    player_state: Dict[str, Any]
    message: str
    session_id: Optional[str] = None
    action: Optional[str] = Field(None, description="Optional explicit PDDL action to execute; bypasses NLU when valid.")
    debug: bool = False


class SocialMessageResponse(BaseModel):
    status: str
    session_id: str
    reply: Optional[Any] = None
    social_state: Dict[str, Any] = Field(default_factory=dict)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    image_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    debug: Optional[Dict[str, Any]] = None


class QuestAcceptRequest(BaseModel):
    quest_goal: str
    quest_name: str
    player_state: Dict[str, Any]
    social_state: Dict[str, Any] = {}
    oracle_mode: bool = True


class QuestAcceptResponse(BaseModel):
    status: str
    plan: List[str] = []
    quest: List[Dict[str, Any]] = []
    payload: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None


class GraphRequest(BaseModel):
    current_location: str
    discovered: List[str] = []
    target_node: Optional[str] = None


class GraphResponse(BaseModel):
    status: str
    graph: str
    error: Optional[str] = None


class SocialGraphRequest(BaseModel):
    persona_id: str
    social_state: Dict[str, Any]
    target_goal: Optional[str] = None

# === Social session helpers ===
def _session_key(persona_id: str, session_id: Optional[str]) -> str:
    return f"{persona_id}:{session_id or 'default'}"


def _normalize_session_id(session_id: Optional[str]) -> Optional[str]:
    if session_id is None:
        return None
    normalized = str(session_id).strip()
    return normalized or None


def _resolve_session_id(
    session_id: Optional[str],
    social_state: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    return _normalize_session_id(session_id) or _normalize_session_id(
        (social_state or {}).get("session_id")
    )


async def _get_session(
    persona_id: str, session_id: Optional[str], default_state: Dict[str, Any]
) -> Dict[str, Any]:
    key = _session_key(persona_id, session_id)
    return await SESSION_STORE.get_or_create(key, default_state)


async def _save_session(
    persona_id: str, session_id: Optional[str], state: Dict[str, Any]
) -> None:
    key = _session_key(persona_id, session_id)
    await SESSION_STORE.set(key, state)


def _has_item(player_state: Dict[str, Any], item_id: str) -> bool:
    inv = player_state.get("inventory", {}) if isinstance(player_state, dict) else {}
    items = inv.get("items", {})
    return items.get(item_id, 0) > 0


def _public_persona_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "persona_name": meta.get("persona_name"),
        "tags": meta.get("tags", []),
        "has_v2_behavior": bool(meta.get("has_v2_behavior", False)),
    }


def _client_social_state(
    session: Dict[str, Any],
    session_id: str,
    include_debug: bool = False,
) -> Dict[str, Any]:
    state_payload = SocialState.from_dict(session).to_dict()
    state_payload["session_id"] = session_id
    state_payload["current_location"] = session.get("current_location", "unknown")
    if include_debug:
        state_payload["active_persona"] = session.get(
            "active_persona", state_payload.get("persona_id", "")
        )
        state_payload["available_moves"] = list(session.get("available_moves", []))
        state_payload["metadata"] = session.get("metadata", {})
    return state_payload


def _social_debug_payload(
    session: Dict[str, Any],
    include_persona_metadata: bool = False,
) -> Optional[Dict[str, Any]]:
    debug_payload: Dict[str, Any] = {}
    if include_persona_metadata:
        debug_payload["persona_metadata"] = session.get("metadata", {})
    if "available_moves" in session:
        debug_payload["available_moves"] = list(session.get("available_moves", []))
    return debug_payload or None


def _compute_available_moves(
    persona_id: str,
    state: SocialState,
    session: Dict[str, Any],
    player_state: Optional[Dict[str, Any]] = None,
) -> List[str]:
    de = _get_dialogue_engine(persona_id)
    if de:
        return [m.pddl_str for m in de.get_valid_moves(state)]
    state_for_moves = session.copy()
    state_for_moves["player_data"] = player_state or {}
    return GAME_ENGINE.get_valid_moves(state_for_moves)


# Explicit action guards for UI shortcuts (bypass NLU but keep sanity checks)
MANUAL_ACTION_GUARDS = {
    "activate-trigger player ctx_neutral_talk trig_find_coin cpt_shadow_token": (
        lambda sess, player: "cpt_shadow_rumor" in sess.get("concepts", []) and _has_item(player, "item_shadow_coin")
    ),
    "apply-combo-concept player ctx_neutral_talk ctx_shadow_entry cpt_shadow_rumor cpt_shadow_token": (
        lambda sess, _player: "cpt_shadow_rumor" in sess.get("concepts", []) and "cpt_shadow_token" in sess.get("concepts", [])
    ),
}

# --- Context helpers ---
def _is_context_reachable(ctx_id: str, contexts_map: Dict[str, Any], concepts: List[str]) -> bool:
    ctx = contexts_map.get(ctx_id, {})
    props = ctx.get("properties", {})
    req = props.get("required_concept")
    if req and req not in concepts:
        return False
    combo = props.get("required_combo")
    if combo and not all(c in concepts for c in combo):
        return False
    return True


def _maybe_update_target_goal(social_state: Dict[str, Any]) -> None:
    contexts_map = social_state.get("metadata", {}).get("contexts", {})
    current_ctx = social_state.get("current_context")
    if not current_ctx or current_ctx not in contexts_map:
        return
    props = contexts_map[current_ctx].get("properties", {})
    hint = props.get("target_goal_hint")
    if not hint:
        return
    if _is_context_reachable(hint, contexts_map, social_state.get("concepts", [])):
        social_state["target_goal"] = hint


# === Helpers (wrappers around shared libs) ===
def load_world_ent() -> WorldGraph:
    return load_world(WORLD_CONFIG_PATH)


async def _run_blocking(func, *args, **kwargs):
    """Run a blocking call in the default threadpool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


# === Endpoints ===
@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        version=__version__,
        up_available=True,
        personas_loaded=len(DIALOGUE_GRAPHS),
        persona_ids=sorted(DIALOGUE_GRAPHS),
    )


@app.get("/world/state")
async def world_state(player_id: str = "player_001", location: str = "forest_entrance", goal: Optional[str] = None):
    """Return world slice for UI navigation."""
    request_id = str(uuid.uuid4())
    start_ts = datetime.now(timezone.utc)
    try:
        world = load_world_ent()
        # Minimal player init
        player = PlayerState(player_id=player_id, current_location=location)
        npcs, exits, items = collect_location_data(world, player.current_location, goal)
        available_quests = collect_available_quests(world, player)

        duration_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000
        return {
            "status": "success",
            "request_id": request_id,
            "metadata": {
                "version": __version__,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "player_id": player_id,
                "goal": goal,
                "location": location,
                "available_quests": available_quests,
                "npcs_nearby": npcs,
                "exits": exits,
                "items_nearby": items,
            },
            "npcs_nearby": npcs,
            "exits": exits,
            "items_nearby": items,
            "duration_ms": duration_ms,
        }
    except Exception as e:
        logger.error(f"/world/state failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class LocationImageRequest(BaseModel):
    location_id: str


@app.post("/world/image")
async def world_image(request: LocationImageRequest):
    """Generate (or return cached) location image. Blocks until ready.
    If the location has an NPC with a reference image, renders an establishing shot with that character.
    """
    loc_data = orchestrator.locations_data.get(request.location_id, {})
    loc_name = loc_data.get("name", request.location_id.replace("_", " ").title())
    loc_desc = loc_data.get("description", "An adventurous location.")

    # Collect ALL NPCs at this location for the establishing shot.
    npc_list = []
    try:
        world = load_world_ent()
        npcs, _, _ = collect_location_data(world, request.location_id)
        for npc in npcs:
            world_node = world.get_node(npc["id"])
            explicit_persona = world_node.properties.get("social_persona") if world_node else None
            if explicit_persona:
                persona_data = orchestrator.personas_data.get(explicit_persona, {})
                image_ref = persona_data.get("properties", {}).get("image_reference")
                npc_list.append({
                    "name": persona_data.get("name", npc.get("name", explicit_persona)),
                    "desc": persona_data.get("visual_appearance") or persona_data.get("description", ""),
                    "ref_path": str(Path("npc_engine/config/social_world/nodes/personas") / image_ref) if image_ref else None,
                })
            elif npc.get("description") or npc.get("personality"):
                # No explicit persona — use NPC's own world description
                npc_list.append({
                    "name": npc.get("name", ""),
                    "desc": npc.get("personality") or npc.get("description", ""),
                    "ref_path": None,
                })
    except Exception as exc:
        logger.warning(f"[world/image] NPC lookup failed: {exc}")

    loop = asyncio.get_event_loop()
    image_path = await loop.run_in_executor(
        None,
        functools.partial(
            VIS_GEN.generate_location_visual,
            request.location_id, loc_name, loc_desc,
            "Fantasy World", None,
            npc_list or None,
        ),
    )
    return {"image_path": image_path}


@app.post("/world/graph", response_model=GraphResponse)
async def world_graph(request: GraphRequest):
    """Return DOT graph for world map."""
    try:
        graph = GAME_ENGINE.render_world_graph(request.current_location, request.discovered, target_node=request.target_node)
        return GraphResponse(status="success", graph=graph.source)
    except Exception as e:
        logger.error(f"/world/graph failed: {e}", exc_info=True)
        return GraphResponse(status="error", graph="", error=str(e))


@app.post("/plan/exploration", response_model=PlanResponse)
async def plan_exploration(request: PlanRequest):
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            functools.partial(
                process_request_lib,
                request.input_json,
                WORLD_CONFIG_PATH,
                oracle_mode=request.oracle_mode,
            ),
        )
        return PlanResponse(**result)
    except Exception as e:
        logger.error(f"/plan/exploration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/quest/difficulty", response_model=QuestDifficultyResponse)
async def quest_difficulty(request: QuestDifficultyRequest):
    try:
        goal = request.goal
        if not goal:
            return QuestDifficultyResponse(status="ok", concept="cpt_quest_none", plan_length=0)
        player = PlayerState(player_id="player_001", current_location="forest_entrance")
        player.goal = goal
        if QUEST_PLANNER:
            concept = await QUEST_PLANNER.assess_difficulty(player)
        else:
            world = load_world_ent()
            concept = execute_hook("analyze_quest_difficulty", player, world)
        return QuestDifficultyResponse(status="ok", concept=concept, plan_length=0)
    except Exception as e:
        logger.error(f"/quest/difficulty failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/quest/accept", response_model=QuestAcceptResponse)
async def quest_accept(request: QuestAcceptRequest):
    """
    Accept a quest: set goal, plan (oracle), and generate mission narrative payload.
    """
    req_id = str(uuid.uuid4())
    start_ts = datetime.now(timezone.utc)
    try:
        player_data = request.player_state.copy()
        player_data["goal"] = request.quest_goal
        player, goal = load_player_from_json_data(player_data)
        if QUEST_PLANNER:
            quest_plan = await QUEST_PLANNER.plan_quest(player, goal, oracle_mode=request.oracle_mode)
            plan_result = quest_plan.steps or None
            quest_steps = quest_plan.quest_steps
            error_msg = quest_plan.error
        else:
            world = load_world_ent()
            plan_result, quest_steps, error_msg = generate_plan_and_quest(world, player, goal, request.oracle_mode)
        payload = social_llm.generate_quest_mission(request.social_state, plan_result or [], request.quest_name)
        meta = {
            "request_id": req_id,
            "duration_ms": (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000,
            "error": error_msg,
            "oracle_used": request.oracle_mode,
            "goal": goal,
        }
        return QuestAcceptResponse(
            status="success" if plan_result is not None else "failure",
            plan=plan_result or [],
            quest=quest_steps,
            payload=payload,
            metadata=meta,
            error=error_msg if plan_result is None else None,
        )
    except Exception as e:
        logger.error(f"/quest/accept failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/process", response_model=PlanResponse)
async def process_endpoint(request: PlanRequest):
    """Compatibility endpoint mirroring /plan/exploration."""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            functools.partial(
                process_request_lib,
                request.input_json,
                WORLD_CONFIG_PATH,
                oracle_mode=request.oracle_mode,
            ),
        )
        return PlanResponse(**result)
    except Exception as e:
        logger.error(f"/process failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/social/init", response_model=SocialInitResponse)
async def social_init(request: SocialInitRequest):
    """Return persona metadata/start context for social interactions."""
    request_id = str(uuid.uuid4())
    start_ts = datetime.now(timezone.utc)
    try:
        session_id = _resolve_session_id(request.session_id) or str(uuid.uuid4())
        orch = PDDLOrchestrator()
        meta = orch.get_persona_metadata(request.persona_id)
        start_ctx = request.active_context or meta.get("start_context", "ctx_intro")
        target_goal = request.target_goal or meta.get("target_goal", "ctx_core")

        # Build typed SocialState — single source of truth for planning fields
        state = SocialState(
            persona_id=request.persona_id,
            current_context=start_ctx,
            goal_context=target_goal,
            concepts=frozenset(),
            visited_contexts=frozenset([start_ctx]),
            unlocked_contexts=frozenset(),
            exhausted_triggers=frozenset(),
            shared_items=frozenset(),
            current_mood="",
            can_quest=request.can_quest,
            oracle_path=None,
        )

        # Session-layer fields that live alongside the typed state
        current_location = request.player_state.get("location") if request.player_state else "unknown"
        session_extras: Dict[str, Any] = {
            "history": [],
            "metadata": meta,
            "current_location": current_location,
            "active_persona": request.persona_id,
            "available_moves": [],
            "session_id": session_id,
        }

        # Precompute available moves (DialogueEngine when compiled, legacy fallback)
        try:
            session_extras["available_moves"] = _compute_available_moves(
                request.persona_id,
                state,
                {**state.to_dict(), **session_extras},
                request.player_state,
            )
        except Exception:
            pass

        # Inject quest-difficulty concept if applicable
        if request.can_quest and request.player_state:
            try:
                player, _goal = load_player_from_json_data(request.player_state)
                player.goal = _goal
                if QUEST_PLANNER:
                    quest_concept = await QUEST_PLANNER.assess_difficulty(player)
                else:
                    world = load_world_ent()
                    quest_concept = execute_hook("analyze_quest_difficulty", player, world)
                if quest_concept and quest_concept != "cpt_quest_none":
                    state = state.with_concept(quest_concept)
            except Exception:
                pass

        contexts_map = meta.get("contexts", {})

        def _is_reachable(ctx_id: str) -> bool:
            ctx = contexts_map.get(ctx_id, {})
            props = ctx.get("properties", {})
            req = props.get("required_concept")
            if req and req not in state.concepts:
                return False
            combo = props.get("required_combo")
            if combo and not all(c in state.concepts for c in combo):
                return False
            return True

        if not _is_reachable(state.goal_context):
            start_ctx_data = contexts_map.get(start_ctx, {})
            for conn in start_ctx_data.get("connections", []):
                cand = conn.get("to")
                if cand and _is_reachable(cand):
                    state = state.with_goal(cand)
                    break

        # _maybe_update_target_goal expects dict — pass merged view
        social_state = {**state.to_dict(), **session_extras}
        _maybe_update_target_goal(social_state)
        # Sync goal back if helper changed it
        if social_state.get("target_goal") != state.goal_context:
            state = state.with_goal(social_state["target_goal"])

        target_goal = state.goal_context

        # Oracle preview of requirements for intro (best-effort)
        quest_keys = []
        has_secrets = bool(meta.get("secrets"))
        if request.can_quest and not has_secrets:
            try:
                res = GAME_ENGINE.get_path_requirements(
                    start_ctx, target_goal, map_key="contexts", state=social_state
                )
                quest_keys = res[0] if res else []
            except Exception:
                quest_keys = []

        reply_payload = await _run_blocking(
            social_llm.generate_quest_intro, social_state, quest_keys, target_goal
        )

        image_path = None
        try:
            persona_data = orchestrator.personas_data.get(request.persona_id, {})
            persona_name = persona_data.get("name", request.persona_id)
            persona_desc = persona_data.get("visual_appearance") or persona_data.get("description", "A mysterious figure.")
            image_ref = persona_data.get("properties", {}).get("image_reference")
            image_ref_path = None
            if image_ref:
                image_ref_path = str(Path("npc_engine/config/social_world/nodes/personas") / image_ref)
            loc_data = orchestrator.locations_data.get(current_location, {})
            loc_name = loc_data.get("name", current_location)
            image_path = await _run_blocking(
                VIS_GEN.generate_scene_visual,
                reply_payload.get("scene_description", ""),
                persona_name,
                persona_desc,
                loc_name,
                image_ref_path=image_ref_path,
                location_ref_path=None,
            )
        except Exception:
            image_path = None

        history = [{"role": "assistant", "content": reply_payload, "image": image_path}] if reply_payload else []
        session_extras["history"] = history

        # Persist: merge typed state back to dict for the session store
        full_session = {**state.to_dict(), **session_extras}
        await _save_session(request.persona_id, session_id, full_session)

        response_state = _client_social_state(
            full_session, session_id, include_debug=request.debug
        )
        response_debug = (
            _social_debug_payload(full_session, include_persona_metadata=True)
            if request.debug
            else None
        )

        duration_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000
        return SocialInitResponse(
            status="success",
            session_id=session_id,
            persona_id=request.persona_id,
            start_context=start_ctx,
            target_goal=target_goal,
            metadata=_public_persona_metadata(meta),
            social_state=response_state,
            history=history,
            reply=reply_payload,
            image_path=image_path,
            request_id=request_id,
            duration_ms=duration_ms,
            can_quest=request.can_quest,
            debug=response_debug,
        )
    except Exception as e:
        logger.error(f"/social/init failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/social/message", response_model=SocialMessageResponse)
async def social_message(request: SocialMessageRequest):
    """Social dialogue backend using GameEngine + LLM."""
    request_id = str(uuid.uuid4())
    start_ts = datetime.now(timezone.utc)
    try:
        persona_id = request.persona_id
        session_id = _resolve_session_id(request.session_id, request.social_state)

        base_state = {
            **SocialState.from_dict({**request.social_state, "persona_id": persona_id}).to_dict(),
            "history": request.social_state.get("history", []),
            "metadata": request.social_state.get("metadata", {}),
            "active_persona": request.social_state.get("active_persona", persona_id),
            "current_location": request.player_state.get("location", "unknown"),
            "session_id": session_id,
        }
        session = await _get_session(persona_id, session_id, base_state)
        session["session_id"] = session_id
        # Session store is the source of truth once the session exists.
        session["current_location"] = request.player_state.get(
            "location", session.get("current_location", "unknown")
        )
        state = SocialState.from_dict({**session, "persona_id": persona_id})

        user_msg = {"role": "user", "content": request.message}
        session.setdefault("history", []).append(user_msg)

        # Compute available moves
        de = _get_dialogue_engine(persona_id)
        if de:
            typed_moves: list[DialogueMove] = de.get_valid_moves(state)
            valid_moves: list[str] = [m.pddl_str for m in typed_moves]
            _move_map: dict[str, DialogueMove] = {m.pddl_str: m for m in typed_moves}
        else:
            state_for_moves = session.copy()
            state_for_moves["player_data"] = request.player_state
            valid_moves = GAME_ENGINE.get_valid_moves(state_for_moves)
            _move_map = {}

        # Optional explicit action bypass (e.g., UI shortcut like sharing the coin)
        chosen_action = None
        if request.action:
            guard = MANUAL_ACTION_GUARDS.get(request.action)
            if request.action in valid_moves or (guard and guard(session, request.player_state)):
                chosen_action = request.action
                logger.info(f"[social_message] Explicit action accepted: {chosen_action}")
            else:
                logger.info(f"[social_message] Explicit action rejected (not valid or guard failed): {request.action}")
        if not chosen_action:
            # Fallback to NLU
            nlu_action = social_llm.get_social_intent(request.message, session, valid_moves)
            if nlu_action and nlu_action in valid_moves:
                chosen_action = nlu_action

        if chosen_action:
            if de and chosen_action in _move_map:
                # Pure-function FSM: produce new state, merge into session
                new_state = de.apply_move(_move_map[chosen_action], state)
                session.update(new_state.to_dict())
            else:
                GAME_ENGINE.apply_action(chosen_action, session)
            # do_act_* are pure narrative — no PDDL state change, don't count as progress
            if not chosen_action.startswith("do_"):
                session['hint_level'] = 0
            else:
                session['hint_level'] = min(int(session.get('hint_level', 0)) + 1, 3)
        else:
            chosen_action = None
            # Player is stuck — escalate hint level (cap at 3: direct)
            session['hint_level'] = min(int(session.get('hint_level', 0)) + 1, 3)

        # Narrative generation
        payload = await _run_blocking(
            social_llm.generate_social_narrative,
            chosen_action or "talk",
            session,
            request.message,
        )

        _maybe_update_target_goal(session)

        current_state = SocialState.from_dict({**session, "persona_id": persona_id})
        try:
            session["available_moves"] = _compute_available_moves(
                persona_id,
                current_state,
                session,
                request.player_state,
            )
        except Exception:
            session.setdefault("available_moves", [])

        image_path = None
        try:
            persona_data = orchestrator.personas_data.get(persona_id, {})
            persona_name = persona_data.get("name", persona_id)
            persona_desc = persona_data.get("visual_appearance") or persona_data.get("description", "A mysterious figure.")
            image_ref = persona_data.get("properties", {}).get("image_reference")
            image_ref_path = None
            if image_ref:
                image_ref_path = str(Path("npc_engine/config/social_world/nodes/personas") / image_ref)

            loc_id = session.get("current_location", "unknown")
            loc_data = orchestrator.locations_data.get(loc_id, {})
            loc_name = loc_data.get("name", loc_id)
            cached_loc = Path("static/images/locations") / f"{loc_id}.png"
            location_ref_path = str(cached_loc) if cached_loc.exists() else None

            scene_desc = payload.get("scene_description", "") if isinstance(payload, dict) else ""
            if not scene_desc:
                scene_desc = f"{persona_name} responds in {loc_name}."
            image_path = await _run_blocking(
                VIS_GEN.generate_scene_visual,
                scene_desc,
                persona_name,
                persona_desc,
                loc_name,
                image_ref_path=image_ref_path,
                location_ref_path=location_ref_path,
            )
        except Exception:
            image_path = None

        session.setdefault("history", []).append({"role": "assistant", "content": payload, "image": image_path})
        await _save_session(persona_id, session_id, session)

        response_state = _client_social_state(
            session,
            session_id or "default",
            include_debug=request.debug,
        )
        response_debug = _social_debug_payload(session) if request.debug else None

        duration_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000
        return SocialMessageResponse(
            status="success",
            session_id=session_id or "default",
            reply=payload,
            social_state=response_state,
            history=session.get("history", []),
            image_path=image_path,
            metadata={
                "request_id": request_id,
                "duration_ms": duration_ms,
                "action": chosen_action,
            },
            error=None,
            debug=response_debug,
        )
    except Exception as e:
        logger.error(f"/social/message failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Compatibility: local process_request wrapper ---
def process_request(input_data: Dict[str, Any], oracle_mode: bool = False) -> Dict[str, Any]:
    """Wrapper around enterprise libs to keep response metadata consistent."""
    request_id = str(uuid.uuid4())
    start_ts = datetime.now(timezone.utc)
    result = process_request_lib(input_data, WORLD_CONFIG_PATH, oracle_mode=oracle_mode)

    duration_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000
    meta = result.setdefault("metadata", {})
    meta.setdefault("version", __version__)
    meta["request_id"] = request_id
    meta["timestamp"] = datetime.now(timezone.utc).isoformat()
    result["duration_ms"] = duration_ms
    result["oracle_used"] = oracle_mode
    return result


@app.post("/social/graph", response_model=GraphResponse)
async def social_graph(request: SocialGraphRequest):
    """Return DOT graph for social state."""
    try:
        target_goal = request.target_goal or request.social_state.get("target_goal") or "ctx_core"
        graph = GAME_ENGINE.render_graph(request.social_state, target_goal)
        return GraphResponse(status="success", graph=graph.source)
    except Exception as e:
        logger.error(f"/social/graph failed: {e}", exc_info=True)
        return GraphResponse(status="error", graph="", error=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
