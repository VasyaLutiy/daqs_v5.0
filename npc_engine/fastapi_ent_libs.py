"""
Shared helpers for the enterprise FastAPI entrypoint.

We keep these utilities here to avoid depending on the legacy
`main_fast.py` module. Functions mirror the stable logic used by
`main_fast_ent.py` for world loading, quest planning, and basic
player state assembly.
"""

from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
from datetime import datetime

from npc_engine.engine.logging_config import logging_manager
from npc_engine.engine.world.graph import WorldGraph, NodeType, LocationNode
from npc_engine.engine.world.player_state import PlayerState
from npc_engine.engine.world.regenerator import WorldRegenerator
from npc_engine.engine.world.loader import load_world_from_flat_yaml
from npc_engine.engine.master.pddl_orchestrator import PDDLOrchestrator
from npc_engine.engine.master.planner import MasterPlanner
from npc_engine.engine.master.quest_generator import QuestGenerator
from npc_engine.version import __version__

DEFAULT_PLAYER_ID = "player_001"
DEFAULT_LOCATION = "forest_entrance"


def load_world(config_path: Path) -> WorldGraph:
    """Load world graph from a flat YAML bundle."""
    return load_world_from_flat_yaml(config_path)


def load_player_from_json_data(data: Dict[str, Any]) -> Tuple[PlayerState, Optional[str]]:
    """Hydrate `PlayerState` from JSON-like dict.

    Supports both nested `inventory.items` and flat `inventory` shapes.
    """
    player = PlayerState(
        player_id=data.get("id", DEFAULT_PLAYER_ID),
        current_location=data.get("location", DEFAULT_LOCATION),
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


def collect_location_data(world: WorldGraph, location_id: str, goal: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Collect NPCs, exits, and items for a given location."""
    npcs_nearby: List[Dict[str, Any]] = []
    exits: List[Dict[str, Any]] = []
    items_nearby: List[Dict[str, Any]] = []

    current_loc_node = world.get_node(location_id)
    if current_loc_node and isinstance(current_loc_node, LocationNode):
        for npc_id in current_loc_node.contained_npcs:
            npc_node = world.get_node(npc_id)
            if npc_node:
                npcs_nearby.append(
                    {
                        "id": npc_id,
                        "name": getattr(npc_node, "name", npc_id),
                        "description": getattr(npc_node, "description", ""),
                        "personality": getattr(npc_node, "personality", ""),
                        "speech_style": getattr(npc_node, "speech_style", ""),
                        "items": npc_node.properties.get("has_items", []),
                        "dialogue_quest": npc_node.properties.get("dialogue_quest", False),
                        "social_persona": npc_node.properties.get("social_persona") or "persona_cyber",
                    }
                )

        connections = world.get_connections_from(location_id)
        for edge in connections:
            target_id = edge.to_node
            target_node = world.get_node(target_id)
            e_type = edge.edge_type.value if hasattr(edge.edge_type, "value") else str(edge.edge_type)
            if target_node and e_type in ["path", "door", "leads_to"]:
                exits.append({"id": target_id, "name": getattr(target_node, "name", target_id)})

        goal_item_id = None
        if goal and goal.startswith("(has-item"):
            import re

            match = re.search(r"\(has-item\s+\w+\s+(\w+)\)", goal)
            if match:
                goal_item_id = match.group(1)

        for item_id in current_loc_node.contained_items:
            item_node = world.get_node(item_id)
            if item_node:
                items_nearby.append(
                    {
                        "id": item_id,
                        "name": getattr(item_node, "name", item_id),
                        "description": getattr(item_node, "description", ""),
                        "is_goal_item": item_id == goal_item_id,
                    }
                )

    return npcs_nearby, exits, items_nearby


def generate_plan_and_quest(world: WorldGraph, player: PlayerState, goal: Optional[str], oracle_mode: bool) -> Tuple[Optional[List[str]], List[Dict[str, Any]], str]:
    """Plan and build quest steps for a player/goal combination."""
    logger = logging_manager.get_component_logger("master")

    if oracle_mode:
        target_world = world
        all_location_ids = [node_id for node_id, node in world.all_nodes.items() if node.type == NodeType.LOCATION]
        player.discovered_locations.update(all_location_ids)
    else:
        regenerator = WorldRegenerator()
        target_world = regenerator.regenerate(world, player)

    if not goal:
        return None, [], "No goal specified."

    mode = "social" if ("ctx_" in goal or "in-context" in goal) else "exploration"

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
        quest_steps = [
            {"step_number": i, "description": step, "action": step.split()[0] if step.split() else "unknown"}
            for i, step in enumerate(plan_result, 1)
        ]

    return plan_result, quest_steps, diagnosis_msg if len(plan_result) == 0 else ""


def collect_available_quests(world: WorldGraph, player: PlayerState) -> List[Dict[str, Any]]:
    """Generate list of available quests based on missing items."""
    available_quests: List[Dict[str, Any]] = []
    player_items = set(player.inventory.items.keys())
    for item_node in world.items.values():
        if item_node.id not in player_items:
            available_quests.append(
                {
                    "id": item_node.id,
                    "name": item_node.name,
                    "goal": f"(has-item {player.player_id} {item_node.id})",
                }
            )
    return available_quests


def process_request(input_data: Dict[str, Any], config_path: Path, oracle_mode: bool = False) -> Dict[str, Any]:
    """Process the input JSON data and return result dict (enterprise copy)."""
    logger = logging_manager.get_component_logger("master")

    try:
        player, goal = load_player_from_json_data(input_data)
        logger.info(f"Player loaded: {player.player_id}, goal: {goal}")
        world = load_world(config_path)

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
                "available_quests": available_quests,
            },
            "plan": plan_result or [],
            "quest": quest_steps,
            "error": error_msg,
            "oracle_used": oracle_mode,
        }

    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        return {
            "status": "error",
            "metadata": {
                "version": __version__,
                "timestamp": datetime.now().isoformat(),
                "player_id": input_data.get("id", "unknown"),
                "goal": input_data.get("goal", "unknown"),
            },
            "plan": [],
            "quest": [],
            "error": str(e),
            "oracle_used": oracle_mode,
        }

