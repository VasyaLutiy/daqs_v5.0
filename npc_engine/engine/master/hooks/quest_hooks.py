from .registry import register_hook
from npc_engine.engine.world.player_state import PlayerState
from npc_engine.engine.world.graph import WorldGraph
from npc_engine.engine.master.pddl_orchestrator import PDDLOrchestrator
from npc_engine.engine.master.planner import MasterPlanner
from npc_engine.engine.world.graph import NodeType
import logging

logger = logging.getLogger("master.hooks")

@register_hook("analyze_quest_difficulty")
def analyze_quest_difficulty(player: PlayerState, world: WorldGraph) -> str:
    """
    Analyzes the complexity of the player's current goal via PDDL planning.
    Returns a PDDL concept ID (e.g., 'cpt_quest_hard').
    """
    if not player.goal:
        return "cpt_quest_none"

    logger.info(f"Hook: Analyzing quest difficulty for {player.player_id}, goal: {player.goal}")

    # Initialize planning tools
    orchestrator = PDDLOrchestrator()
    planner = MasterPlanner()

    # ORACLE MODE: Grant full knowledge for assessment
    original_knowledge = player.discovered_locations.copy()
    all_location_ids = [node_id for node_id, node in world.all_nodes.items() if node.type == NodeType.LOCATION]
    player.discovered_locations.update(all_location_ids)

    try:
        # Generate and solve PDDL
        domain, problem = orchestrator.generate("exploration", player, world, player.goal)
        plan, msg = planner.solve(domain, problem, player.player_id, player_state=player)
        
        if plan is None:
            logger.warning("Hook: Quest is currently impossible.")
            return "cpt_quest_impossible"
            
        steps = len(plan)
        logger.info(f"Hook: Plan found with {steps} steps.")

        # Complexity Mapping
        if steps == 0:
            return "cpt_quest_none"
        elif steps < 5:
            return "cpt_quest_easy"
        else:
            return "cpt_quest_hard"

    finally:
        # Crucial: Restore original player knowledge
        player.discovered_locations = original_knowledge
