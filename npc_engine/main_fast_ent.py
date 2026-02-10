"""
Enterprise FastAPI entrypoint: API-first planning/service layer.
Keeps all planning/world logic server-side; clients call HTTP endpoints.
"""

import uuid
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from npc_engine.bootstrap import init_logging
from npc_engine.engine.logging_config import logging_manager
from npc_engine.engine.world.graph import WorldGraph
from npc_engine.engine.world.player_state import PlayerState
from npc_engine.engine.world.regenerator import WorldRegenerator
from npc_engine.engine.world.loader import load_world_from_flat_yaml
from npc_engine.engine.master.pddl_orchestrator import PDDLOrchestrator
from npc_engine.engine.master.planner import MasterPlanner
from npc_engine.engine.master.hooks.registry import execute_hook
import npc_engine.engine.master.hooks.quest_hooks  # ensure hooks registered
from npc_engine.version import __version__

from gamemaster import social_llm
from gamemaster.prompt_orchestrator import orchestrator
from gamemaster.visual_generator import VisualGenerator
from gamemaster.engine_core import GameEngine

init_logging()
logger = logging_manager.get_component_logger("master")

BASE_DIR = Path(__file__).resolve().parent
WORLD_CONFIG_PATH = BASE_DIR / "config" / "world"
CONFIG_DIR = BASE_DIR / "config"

app = FastAPI(title="NPC Engine API (Enterprise)", version=__version__)
SOCIAL_SESSIONS: Dict[str, Dict[str, Any]] = {}
GAME_ENGINE = GameEngine(CONFIG_DIR)
VIS_GEN = VisualGenerator()


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


class SocialInitRequest(BaseModel):
    persona_id: str = Field(..., description="Persona identifier")
    active_context: Optional[str] = None
    target_goal: Optional[str] = None
    can_quest: bool = True
    player_state: Optional[Dict[str, Any]] = None
    player_state: Optional[Dict[str, Any]] = None


class SocialInitResponse(BaseModel):
    status: str
    persona_id: str
    start_context: str
    target_goal: str
    metadata: Dict[str, Any] = {}
    social_state: Dict[str, Any] = {}
    history: List[Dict[str, Any]] = []
    reply: Optional[Any] = None
    image_path: Optional[str] = None
    request_id: Optional[str] = None
    duration_ms: Optional[float] = None
    can_quest: bool = True


class SocialMessageRequest(BaseModel):
    persona_id: str
    social_state: Dict[str, Any]
    player_state: Dict[str, Any]
    message: str
    session_id: Optional[str] = None
    action: Optional[str] = Field(None, description="Optional explicit PDDL action to execute; bypasses NLU when valid.")


class SocialMessageResponse(BaseModel):
    status: str
    reply: Optional[Any] = None
    social_state: Dict[str, Any] = {}
    history: List[Dict[str, Any]] = []
    image_path: Optional[str] = None
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None


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


def _get_session(persona_id: str, session_id: Optional[str], default_state: Dict[str, Any]) -> Dict[str, Any]:
    key = _session_key(persona_id, session_id)
    if key not in SOCIAL_SESSIONS:
        SOCIAL_SESSIONS[key] = default_state
    return SOCIAL_SESSIONS[key]


def _save_session(persona_id: str, session_id: Optional[str], state: Dict[str, Any]) -> None:
    key = _session_key(persona_id, session_id)
    SOCIAL_SESSIONS[key] = state


def _has_item(player_state: Dict[str, Any], item_id: str) -> bool:
    inv = player_state.get("inventory", {}) if isinstance(player_state, dict) else {}
    items = inv.get("items", {})
    return items.get(item_id, 0) > 0


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


def _apply_shadow_goal_logic(social_state: Dict[str, Any]) -> None:
    """
    Special-case progression for Dolores shadow path:
    if the player has rumor, token, and quest_hard while in shadow_entry,
    bump target_goal to ctx_joined and grant partnership offer concept.
    """
    return  # use StateManager/valid moves instead of manual injections

# === Helpers ===
def load_world() -> WorldGraph:
    return load_world_from_flat_yaml(WORLD_CONFIG_PATH)


def load_player_from_json_data(data: Dict[str, Any]) -> Tuple[PlayerState, Optional[str]]:
    player = PlayerState(
        player_id=data.get("id", "player_001"),
        current_location=data.get("location", "forest_entrance")
    )
    for ab_id, level in data.get("abilities", {}).items():
        player.add_ability(ab_id, int(level))
    inventory_data = data.get("inventory", {})
    if "items" in inventory_data:
        for item_id, count in inventory_data["items"].items():
            player.inventory.add_item(item_id, int(count))
    else:
        for item_id, count in inventory_data.items():
            player.inventory.add_item(item_id, int(count))
    knowledge = data.get("knowledge", {})
    player.discovered_locations = set(knowledge.get("discovered_locations", []))
    player.visited_locations = set(knowledge.get("visited_locations", []))
    player.known_npcs = set(knowledge.get("known_npcs", []))
    history = data.get("history", {})
    player.defeated_enemies = set(history.get("defeated_enemies", []))
    player.avoided_enemies = set(history.get("avoided_enemies", []))
    player.talked_to = set(history.get("talked_to", []))
    quest_state = data.get("quest_state", {})
    player.completed_quests = set(quest_state.get("completed_quests", []))
    goal = data.get("goal")
    return player, goal


def collect_location_data(world: WorldGraph, location_id: str, goal: Optional[str] = None):
    """Collect NPCs, exits, and items for a given location."""
    from npc_engine.main_fast import collect_location_data as _cld
    return _cld(world, location_id, goal)


def generate_plan_and_quest(world: WorldGraph, player: PlayerState, goal: Optional[str], oracle_mode: bool):
    """Reuse logic from main_fast generate_plan_and_quest."""
    from npc_engine.main_fast import generate_plan_and_quest as _gpq
    return _gpq(world, player, goal, oracle_mode)


def collect_available_quests(world: WorldGraph, player: PlayerState) -> List[Dict[str, Any]]:
    """Reuse available quest discovery from main_fast."""
    from npc_engine.main_fast import collect_available_quests as _caq
    return _caq(world, player)


# === Endpoints ===
@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version=__version__, up_available=True)


@app.get("/world/state")
async def world_state(player_id: str = "player_001", location: str = "forest_entrance", goal: Optional[str] = None):
    """Return world slice for UI navigation."""
    request_id = str(uuid.uuid4())
    start_ts = datetime.utcnow()
    try:
        world = load_world()
        # Minimal player init
        player = PlayerState(player_id=player_id, current_location=location)
        npcs, exits, items = collect_location_data(world, player.current_location, goal)
        available_quests = collect_available_quests(world, player)
        duration_ms = (datetime.utcnow() - start_ts).total_seconds() * 1000
        return {
            "status": "success",
            "request_id": request_id,
            "metadata": {
                "version": __version__,
                "timestamp": datetime.utcnow().isoformat(),
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
        result = process_request(request.input_json, oracle_mode=request.oracle_mode)
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
        world = load_world()
        player = PlayerState(player_id="player_001", current_location="forest_entrance")
        player.goal = goal
        # Use the advanced hook via execute_hook
        concept = execute_hook("analyze_quest_difficulty", player, world)
        # No direct plan length without solving again; leave 0 for now
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
    start_ts = datetime.utcnow()
    try:
        player_data = request.player_state.copy()
        player_data["goal"] = request.quest_goal
        player, goal = load_player_from_json_data(player_data)
        world = load_world()
        plan_result, quest_steps, error_msg = generate_plan_and_quest(world, player, goal, request.oracle_mode)
        payload = social_llm.generate_quest_mission(request.social_state, plan_result or [], request.quest_name)
        meta = {
            "request_id": req_id,
            "duration_ms": (datetime.utcnow() - start_ts).total_seconds() * 1000,
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
        result = process_request(request.input_json, oracle_mode=request.oracle_mode)
        return PlanResponse(**result)
    except Exception as e:
        logger.error(f"/process failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/social/init", response_model=SocialInitResponse)
async def social_init(request: SocialInitRequest):
    """Return persona metadata/start context for social interactions."""
    request_id = str(uuid.uuid4())
    start_ts = datetime.utcnow()
    try:
        orch = PDDLOrchestrator()
        meta = orch.get_persona_metadata(request.persona_id)
        start_ctx = request.active_context or meta.get("start_context", "ctx_intro")
        target_goal = request.target_goal or meta.get("target_goal", "ctx_core")
        social_state = {
            "persona_id": request.persona_id,
            "current_context": start_ctx,
            "target_goal": target_goal,
            "concepts": [],
            "visited_contexts": [start_ctx],
            "unlocked_contexts": [],
            "exhausted_triggers": [],
            "shared_items": [],
            "history": [],
            "metadata": meta,
            "current_location": request.player_state.get("location") if request.player_state else "unknown",
            "active_persona": request.persona_id,
            "can_quest": request.can_quest,
        }

        # Precompute available moves for client-side action shortcuts
        try:
            state_for_moves = social_state.copy()
            state_for_moves["player_data"] = request.player_state or {}
            social_state["available_moves"] = GAME_ENGINE.get_valid_moves(state_for_moves)
        except Exception:
            social_state["available_moves"] = []

        quest_concept = None
        if request.can_quest and request.player_state:
            try:
                world = load_world()
                player, goal = load_player_from_json_data(request.player_state)
                player.goal = goal
                quest_concept = execute_hook("analyze_quest_difficulty", player, world)
                if quest_concept and quest_concept != "cpt_quest_none":
                    if quest_concept not in social_state["concepts"]:
                        social_state["concepts"].append(quest_concept)
            except Exception:
                quest_concept = None

        contexts_map = meta.get("contexts", {})

        def _is_reachable(ctx_id: str) -> bool:
            ctx = contexts_map.get(ctx_id, {})
            props = ctx.get("properties", {})
            req = props.get("required_concept")
            if req and req not in social_state.get("concepts", []):
                return False
            combo = props.get("required_combo")
            if combo and not all(c in social_state.get("concepts", []) for c in combo):
                return False
            return True

        if not _is_reachable(target_goal):
            start_ctx_data = contexts_map.get(start_ctx, {})
            for conn in start_ctx_data.get("connections", []):
                cand = conn.get("to")
                if cand and _is_reachable(cand):
                    target_goal = cand
                    social_state["target_goal"] = cand
                    break

        _apply_shadow_goal_logic(social_state)
        _maybe_update_target_goal(social_state)

        # Oracle preview of requirements for intro (best-effort)
        quest_keys = []
        has_secrets = bool(meta.get("secrets"))
        if request.can_quest and not has_secrets:
            try:
                res = GAME_ENGINE.get_path_requirements(start_ctx, target_goal, map_key="contexts", state=social_state)
                quest_keys = res[0] if res else []
            except Exception:
                quest_keys = []

        reply_payload = social_llm.generate_quest_intro(social_state, quest_keys, target_goal)

        image_path = None
        try:
            persona_data = orchestrator.personas_data.get(request.persona_id, {})
            persona_name = persona_data.get("name", request.persona_id)
            persona_desc = persona_data.get("description", "A mysterious figure.")
            image_ref = persona_data.get("properties", {}).get("image_reference")
            image_ref_path = None
            if image_ref:
                image_ref_path = str(Path("npc_engine/config/social_world/nodes/personas") / image_ref)
            loc_id = social_state.get("current_location", "unknown")
            loc_data = orchestrator.locations_data.get(loc_id, {})
            loc_name = loc_data.get("name", loc_id)
            image_path = VIS_GEN.generate_scene_visual(
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
        social_state["history"] = history
        _save_session(request.persona_id, None, social_state)

        duration_ms = (datetime.utcnow() - start_ts).total_seconds() * 1000
        return SocialInitResponse(
            status="success",
            persona_id=request.persona_id,
            start_context=start_ctx,
            target_goal=target_goal,
            metadata=meta,
            social_state=social_state,
            history=history,
            reply=reply_payload,
            image_path=image_path,
            request_id=request_id,
            duration_ms=duration_ms,
            can_quest=request.can_quest,
        )
    except Exception as e:
        logger.error(f"/social/init failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/social/message", response_model=SocialMessageResponse)
async def social_message(request: SocialMessageRequest):
    """Social dialogue backend using GameEngine + LLM."""
    request_id = str(uuid.uuid4())
    start_ts = datetime.utcnow()
    try:
        persona_id = request.persona_id
        base_state = {
            "persona_id": persona_id,
            "current_context": request.social_state.get("current_context", "ctx_intro"),
            "target_goal": request.social_state.get("target_goal", "ctx_core"),
            "concepts": request.social_state.get("concepts", []),
            "visited_contexts": request.social_state.get("visited_contexts", []),
            "unlocked_contexts": request.social_state.get("unlocked_contexts", []),
            "exhausted_triggers": request.social_state.get("exhausted_triggers", []),
            "shared_items": request.social_state.get("shared_items", []),
            "history": request.social_state.get("history", []),
            "metadata": request.social_state.get("metadata", {}),
            "active_persona": request.social_state.get("active_persona", persona_id),
            "current_location": request.player_state.get("location", "unknown"),
        }
        session = _get_session(persona_id, request.session_id, base_state)

        user_msg = {"role": "user", "content": request.message}
        session.setdefault("history", []).append(user_msg)

        # Compute available moves
        state_for_moves = session.copy()
        state_for_moves["player_data"] = request.player_state
        valid_moves = GAME_ENGINE.get_valid_moves(state_for_moves)

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
            nlu_action = social_llm.get_social_intent(request.message, state_for_moves, valid_moves)
            if nlu_action and nlu_action in valid_moves:
                chosen_action = nlu_action

        if chosen_action:
            GAME_ENGINE.apply_action(chosen_action, session)
        else:
            chosen_action = None

        # Narrative generation
        payload = social_llm.generate_social_narrative(chosen_action or "talk", session, request.message)

        _apply_shadow_goal_logic(session)
        _maybe_update_target_goal(session)

        image_path = None
        try:
            persona_data = orchestrator.personas_data.get(persona_id, {})
            persona_name = persona_data.get("name", persona_id)
            persona_desc = persona_data.get("description", "A mysterious figure.")
            image_ref = persona_data.get("properties", {}).get("image_reference")
            image_ref_path = None
            if image_ref:
                image_ref_path = str(Path("npc_engine/config/social_world/nodes/personas") / image_ref)

            loc_id = session.get("current_location", "unknown")
            loc_data = orchestrator.locations_data.get(loc_id, {})
            loc_name = loc_data.get("name", loc_id)
            cached_loc = Path("static/images/locations") / f"{loc_id}.png"
            location_ref_path = str(cached_loc) if cached_loc.exists() else None

            if "scene_description" in payload:
                image_path = VIS_GEN.generate_scene_visual(
                    payload.get("scene_description", ""),
                    persona_name,
                    persona_desc,
                    loc_name,
                    image_ref_path=image_ref_path,
                    location_ref_path=location_ref_path,
                )
        except Exception:
            image_path = None

        session.setdefault("history", []).append({"role": "assistant", "content": payload, "image": image_path})
        _save_session(persona_id, request.session_id, session)

        duration_ms = (datetime.utcnow() - start_ts).total_seconds() * 1000
        return SocialMessageResponse(
            status="success",
            reply=payload,
            social_state=session,
            history=session.get("history", []),
            image_path=image_path,
            metadata={
                "request_id": request_id,
                "duration_ms": duration_ms,
                "action": chosen_action,
                "valid_moves": valid_moves,
            },
            error=None,
        )
    except Exception as e:
        logger.error(f"/social/message failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Compatibility: reuse process_request from main_fast ---
def process_request(input_data: Dict[str, Any], oracle_mode: bool = False) -> Dict[str, Any]:
    """Thin wrapper calling existing logic from main_fast with request metadata."""
    from npc_engine.main_fast import process_request as _pr

    request_id = str(uuid.uuid4())
    start_ts = datetime.utcnow()
    result = _pr(input_data, oracle_mode=oracle_mode)

    duration_ms = (datetime.utcnow() - start_ts).total_seconds() * 1000
    meta = result.setdefault("metadata", {})
    meta.setdefault("version", __version__)
    meta["request_id"] = request_id
    meta["timestamp"] = datetime.utcnow().isoformat()
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
