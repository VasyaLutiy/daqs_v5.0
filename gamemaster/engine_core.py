from npc_engine.engine.logging_config import get_logger
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import yaml
import graphviz

# Import new manager classes
from npc_engine.engine.gamemaster.cache_manager import CacheManager
from npc_engine.engine.gamemaster.move_validator import MoveValidator
from npc_engine.engine.gamemaster.npc_behavior import NPCBehavior
from npc_engine.engine.gamemaster.state_manager import StateManager
from npc_engine.engine.gamemaster.graph_renderer import GraphRenderer
from npc_engine.engine.gamemaster.path_finder import PathFinder

# PDDL Integration for Oracle
from npc_engine.engine.master.pddl_orchestrator import PDDLOrchestrator
from npc_engine.engine.master.planner import MasterPlanner
from npc_engine.engine.world.player_state import PlayerState

# Logger for abstract world state logic
logger = get_logger("gamemaster.state")

class GameEngine:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir

        # Initialize manager classes
        self.cache_manager = CacheManager(config_dir)
        self.move_validator = MoveValidator(self.cache_manager.cache)
        self.npc_behavior = NPCBehavior()
        self.state_manager = StateManager(self.cache_manager.cache)
        self.graph_renderer = GraphRenderer()
        self.path_finder = PathFinder()

        logger.info("GameEngine: Initialized with manager classes.")

    def reload(self):
        """Force reload of configuration cache."""
        self.cache_manager.reload_cache()
        logger.info("GameEngine: Cache reloaded.")

    # Delegate cache operations to CacheManager
    def _load_cache(self) -> Dict[str, Dict]:
        """Preloads all YAML configs to memory."""
        return self.cache_manager.load_cache()

    @property
    def cache(self) -> Dict[str, Dict]:
        """Access to cached configurations."""
        return self.cache_manager.cache

    def get_valid_moves(self, state: Dict[str, Any]) -> List[str]:
        """Finds valid abstract moves, filtered by inventory and persona tags."""
        return self.move_validator.get_valid_moves(state)

    def apply_action(self, action_str: str, state: Dict[str, Any]):
        """Executes the action on the state dict directly."""
        self.state_manager.apply_action(action_str, state)

    def render_world_graph(self, current_loc: str, discovered_list: list, full_map: bool = False, target_node: str = None) -> graphviz.Digraph:
        """Visualizes the world map. Highlights current location and target goal."""
        return self.graph_renderer.render_world_graph(current_loc, discovered_list, full_map, target_node, self.cache)

    def render_graph(self, state: Dict[str, Any], target_goal: Optional[str] = None) -> graphviz.Digraph:
        """Visualizes the world state using GraphViz."""
        return self.graph_renderer.render_dialogue_graph(state, target_goal, self.cache)

    def get_path_requirements(self, start_node: str, target_node: str, map_key: str = "contexts", state: Optional[Dict[str, Any]] = None) -> Optional[Tuple[List[str], List[str]]]:
        """
        Oracle Logic: Uses PDDL Planning to find logical path and requirements.
        Returns (List of requirements, List of locations) if path found, or None.

        Args:
            start_node (str): Starting node ID
            target_node (str): Target node ID (Goal)
            map_key (str): Map type ("contexts" or "world_map")
            state (Optional[Dict[str, Any]]): Current game state for context information

        Returns:
            Optional[Tuple[List[str], List[str]]]: (requirements, path) if found, None otherwise
        """
        state = state or {}

        if map_key == "contexts":
            # --- PDDL ORACLE (V2) ---
            # Generate PDDL problem for reaching the target
            
            # Construct a temporary PlayerState for the planner
            player = PlayerState(player_id="oracle_bot", current_location="unknown")
            player.known_facts = set(state.get("concepts", []))
            # We assume active_persona is in the state to load correct world
            active_persona = state.get("active_persona", "persona_cyber")
            
            orchestrator = PDDLOrchestrator()
            planner = MasterPlanner()
            
            # Goal: Reach the target context
            # We use 'visited' because 'active-context' changes
            goal_pddl = f"(visited {target_node})"
            
            # Generate Logic
            # We pass 'current_context' in dynamic_state to set start position
            domain, problem = orchestrator.generate(
                mode="social",
                player_state=player,
                world_graph=None,
                goal_pddl=goal_pddl,
                active_persona=active_persona,
                dynamic_state=state # Pass full state including current_context/mood
            )
            
            # Solve
            plan, _ = planner.solve(domain, problem, "oracle_check", player)
            
            if plan:
                # Extract Requirements (Concepts learned/used along the way)
                requirements = []
                path = [start_node]
                
                for step in plan:
                    # step: "learn-concept player ctx cpt"
                    parts = step.replace('(', '').replace(')', '').split()
                    action = parts[0]
                    
                    if action in ["learn-concept", "activate-trigger", "npc-offer", "npc-flirt"]:
                        # The last argument is typically the concept gained
                        concept = parts[-1]
                        requirements.append(concept)
                    elif action == "shift-context":
                        target = parts[-1]
                        path.append(target)
                        
                return (requirements, path)
            else:
                return None # No logical path found

        elif map_key == "world_map":
            # Use PathFinder for world navigation (Legacy/Simple)
            discovered_locations = []
            path = self.path_finder.find_navigation_path(
                start_node, target_node,
                self.cache["world_map"],
                discovered_locations
            )
            if path:
                return ([], path)

        return None  # Path physically impossible
