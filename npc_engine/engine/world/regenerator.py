"""World graph regenerator for personalized player graphs."""

from typing import Optional
from . import logger
from .graph import WorldGraph, NodeState
from .player_state import PlayerState


class WorldRegenerator:
    """Regenerates the world graph based on player state."""

    def regenerate(self, base_world: WorldGraph, player_state: PlayerState) -> WorldGraph:
        """Create a personalized world graph for the player.

        Args:
            base_world: The base world graph
            player_state: Current player state

        Returns:
            Personalized world graph
        """
        logger.debug(f"Regenerating world graph for player {player_state.player_id}")
        logger.debug(f"Base world: {base_world.name} with {len(base_world.all_nodes)} nodes")

        # Process any respawn timers for this player (per-player respawns)
        respawned = player_state.check_and_process_respawns()
        if respawned:
            logger.info(f"Respawned NPCs for player '{player_state.player_id}': {respawned}")

        # For prototype, just return a copy of the base world
        # In full implementation, this would apply diffs and personalization
        personalized = WorldGraph(
            world_id=base_world.world_id,
            name=base_world.name,
            description=base_world.description
        )

        # Copy all nodes
        personalized.all_nodes = base_world.all_nodes.copy()
        personalized.regions = base_world.regions.copy()
        personalized.locations = base_world.locations.copy()
        personalized.objects = base_world.objects.copy()
        personalized.items = base_world.items.copy()
        personalized.npcs = base_world.npcs.copy()
        personalized.edges = base_world.edges.copy()
        personalized.quest_chains = base_world.quest_chains.copy()
        personalized.abilities = base_world.abilities.copy()

        # Apply player-specific changes
        self._apply_player_diffs(personalized, player_state)

        logger.debug(f"Personalized world graph created with {len(personalized.all_nodes)} nodes")
        return personalized

    def _apply_player_diffs(self, world: WorldGraph, player_state: PlayerState):
        """Apply player state changes to the world graph."""
        logger.debug(f"Applying player diffs: {len(player_state.graph_diff.node_states)} node states, "
                    f"{len(player_state.graph_diff.removed_nodes)} removed nodes")
        
        # Update node states based on player progress
        for node_id, state in player_state.graph_diff.node_states.items():
            if node_id in world.all_nodes:
                world.all_nodes[node_id].state = state

        # Remove collected items
        for removed_node in player_state.graph_diff.removed_nodes:
            if removed_node in world.all_nodes:
                del world.all_nodes[removed_node]
            if removed_node in world.items:
                del world.items[removed_node]

        # Update object states
        for obj_id, states in player_state.graph_diff.object_states.items():
            if obj_id in world.all_nodes:
                world.all_nodes[obj_id].custom_states.update(states)
        
        logger.debug("Player diffs applied successfully")