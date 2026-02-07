#!/usr/bin/env python3
"""FastAPI version of NPC Engine for HTTP API access."""

import sys
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
import json
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Initialize logging first
from engine.logging_config import logging_manager
logging_manager.setup_all_loggers()

from engine.world.graph import WorldGraph, WorldNode, NodeType, LocationNode, ItemNode, NPCNode, Edge, EdgeType, Condition
from engine.world.player_state import PlayerState
from engine.world.regenerator import WorldRegenerator
from engine.master.pddl_orchestrator import PDDLOrchestrator
from engine.master.planner import MasterPlanner
from engine.master.quest_generator import QuestGenerator
from engine.world.loader import load_world_from_flat_yaml
from engine.master.hooks.registry import execute_hook # Added
import engine.master.hooks.quest_hooks # Ensure hooks are registered
from version import __version__

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Constants
BASE_DIR = Path(__file__).resolve().parent
WORLD_CONFIG_PATH = BASE_DIR / "config" / "world"
DEFAULT_PLAYER_ID = "player_001"
DEFAULT_LOCATION = "forest_entrance"

app = FastAPI(title="NPC Engine API", version=__version__)

# Initialize services
# No global services for dialogue anymore, logic is handled via PDDLOrchestrator per request

# --- Pydantic Models ---
class ProcessRequest(BaseModel):
    input_json: Dict[str, Any]
    oracle_mode: bool = False

class ProcessResponse(BaseModel):
    status: str
    metadata: Dict[str, Any]
    plan: List[str] = []
    quest: List[Dict[str, Any]] = []
    error: Optional[str] = None
    oracle_used: bool = False

class DialogueStepRequest(BaseModel):
    player_id: str = Field(..., min_length=1)
    current_state: Dict[str, Any]
    location: Optional[str] = None

class DialogueStepResponse(BaseModel):
    status: str  # "success" or "failure"
    action: Optional[str] = None
    pddl_action: Optional[str] = None
    updated_state: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}
    quest_options: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None

# --- Helper Functions ---
def load_player_from_json_data(data: Dict[str, Any]) -> Tuple[PlayerState, Optional[str]]:
    """Load player state and goal from JSON data dict."""
    player = PlayerState(
        player_id=data.get("id", DEFAULT_PLAYER_ID),
        current_location=data.get("location", DEFAULT_LOCATION)
    )
    
    # Load abilities
    for ab_id, level in data.get("abilities", {}).items():
        player.add_ability(ab_id, int(level))
        
    # Load inventory
    inventory_data = data.get("inventory", {})
    if "items" in inventory_data:
        # New nested format
        for item_id, count in inventory_data["items"].items():
            player.inventory.add_item(item_id, int(count))
    else:
        # Old flat format
        for item_id, count in inventory_data.items():
            player.inventory.add_item(item_id, int(count))
        
    # Load knowledge
    knowledge = data.get("knowledge", {})
    player.discovered_locations = set(knowledge.get("discovered_locations", []))
    player.visited_locations = set(knowledge.get("visited_locations", []))
    player.known_npcs = set(knowledge.get("known_npcs", []))
    
    # Load history
    history = data.get("history", {})
    player.defeated_enemies = set(history.get("defeated_enemies", []))
    player.avoided_enemies = set(history.get("avoided_enemies", []))
    player.talked_to = set(history.get("talked_to", []))
    
    # Load quest state
    quest_state = data.get("quest_state", {})
    player.completed_quests = set(quest_state.get("completed_quests", []))
    
    goal = data.get("goal")
    return player, goal

def load_world() -> WorldGraph:
    """Load the world from config."""
    return load_world_from_flat_yaml(WORLD_CONFIG_PATH)

def collect_location_data(world: WorldGraph, location_id: str, goal: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Collect NPCs, exits, and items for a given location."""
    npcs_nearby = []
    exits = []
    items_nearby = []
    
    current_loc_node = world.get_node(location_id)
    if current_loc_node and isinstance(current_loc_node, LocationNode):
        # Collect NPCs
        for npc_id in current_loc_node.contained_npcs:
            npc_node = world.get_node(npc_id)
            if npc_node:
                npcs_nearby.append({
                    "id": npc_id,
                    "name": getattr(npc_node, 'name', npc_id),
                    "description": getattr(npc_node, 'description', ""),
                    "personality": getattr(npc_node, 'personality', ""),
                    "speech_style": getattr(npc_node, 'speech_style', ""),
                    "items": npc_node.properties.get("has_items", []),
                    "dialogue_quest": npc_node.properties.get("dialogue_quest", False),
                    "social_persona": npc_node.properties.get("social_persona", "persona_cyber")
                })
        
        # Collect Exits
        connections = world.get_connections_from(location_id)
        for edge in connections:
            target_id = edge.to_node
            target_node = world.get_node(target_id)
            e_type = edge.edge_type.value if hasattr(edge.edge_type, 'value') else str(edge.edge_type)
            if target_node and e_type in ["path", "door", "leads_to"]:
                exits.append({
                    "id": target_id,
                    "name": getattr(target_node, 'name', target_id)
                })
        
        goal_item_id = None
        if goal and goal.startswith("(has-item"):
            import re
            match = re.search(r'\(has-item\s+\w+\s+(\w+)\)', goal)
            if match:
                goal_item_id = match.group(1)

        # Collect Items
        for item_id in current_loc_node.contained_items:
            item_node = world.get_node(item_id)
            if item_node:
                items_nearby.append({
                    "id": item_id,
                    "name": getattr(item_node, 'name', item_id),
                    "description": getattr(item_node, 'description', ""),
                    "is_goal_item": item_id == goal_item_id
                })
    
    return npcs_nearby, exits, items_nearby

def generate_plan_and_quest(world: WorldGraph, player: PlayerState, goal: Optional[str], oracle_mode: bool) -> Tuple[Optional[List[str]], List[Dict[str, Any]], str]:
    
    logger = logging_manager.get_component_logger('master')
      
    if oracle_mode:
        target_world = world
        all_location_ids = [node_id for node_id, node in world.all_nodes.items() if node.type == NodeType.LOCATION]
        player.discovered_locations.update(all_location_ids)
    else:
        regenerator = WorldRegenerator()
        target_world = regenerator.regenerate(world, player)
    
    if not goal:
        return None, [], "No goal specified."
    
    # Detect mode based on goal
    if "ctx_" in goal or "in-context" in goal:
        mode = "social"
    else:
        mode = "exploration"
    
    logger.info("About to create PDDLOrchestrator")
    pddl_orchestrator = PDDLOrchestrator()
    logger.info("PDDLOrchestrator created, calling generate")
    domain, problem = pddl_orchestrator.generate(mode, player, target_world, goal)
    
    planner = MasterPlanner()
    plan_result, diagnosis_msg = planner.solve(domain, problem, player.player_id, player_state=player)
    
    if plan_result is None:
        return None, [], diagnosis_msg
    
    try:
        quest_gen = QuestGenerator()
        quest_steps = quest_gen.generate_quest(plan_result)
    except Exception as e:
        logger.error(f"Failed to generate quest descriptions: {e}")
        quest_steps = [{"step_number": i, "description": step, "action": step.split()[0] if step.split() else "unknown"} for i, step in enumerate(plan_result, 1)]
    
    return plan_result, quest_steps, diagnosis_msg if len(plan_result) == 0 else ""

def collect_available_quests(world: WorldGraph, player: PlayerState) -> List[Dict[str, Any]]:
    """Generate list of available quests."""
    available_quests = []
    player_items = set(player.inventory.items.keys())
    for item_node in world.items.values():
        if item_node.id not in player_items:
            available_quests.append({
                "id": item_node.id,
                "name": item_node.name,
                "goal": f"(has-item {player.player_id} {item_node.id})"
            })
    return available_quests

def process_request(input_data: Dict[str, Any], oracle_mode: bool = False) -> Dict[str, Any]:
    """Process the input JSON data and return result dict."""
    logger = logging_manager.get_component_logger('master')
    
    try:
        player, goal = load_player_from_json_data(input_data)
        logger.info(f"Player loaded: {player.player_id}, goal: {goal}")
        world = load_world()
        
        plan_result, quest_steps, error_msg = generate_plan_and_quest(world, player, goal, oracle_mode)
        npcs_nearby, exits, items_nearby = collect_location_data(world, player.current_location, goal)
        available_quests = collect_available_quests(world, player)
        
        status = "success" if plan_result is not None else "failure"
        
        return {
            "status": status,
            "metadata": {
                "version": __version__,
                "timestamp": datetime.now().isoformat(),
                "player_id": player.player_id,
                "goal": goal,
                "location": player.current_location,
                "npcs_nearby": npcs_nearby,
                "exits": exits,
                "items_nearby": items_nearby,
                "available_quests": available_quests
            },
            "plan": plan_result or [],
            "quest": quest_steps,
            "error": error_msg,
            "oracle_used": oracle_mode
        }
        
    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        return {
            "status": "error",
            "metadata": {
                "version": __version__,
                "timestamp": datetime.now().isoformat(),
                "player_id": input_data.get("id", "unknown"),
                "goal": input_data.get("goal", "unknown")
            },
            "plan": [],
            "quest": [],
            "error": str(e),
            "oracle_used": oracle_mode
        }

# --- API Endpoints ---
@app.post("/process", response_model=ProcessResponse)
async def process_endpoint(request: ProcessRequest):
    """Process NPC Engine request."""
    result = process_request(request.input_json, oracle_mode=request.oracle_mode)
    return ProcessResponse(**result)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
