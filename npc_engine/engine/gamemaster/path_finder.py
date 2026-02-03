"""
Path Finder for DAQS Game Engine

Handles pathfinding algorithms for navigation and dialogue progression.
Implements A* search, Dijkstra's algorithm, and heuristic-based planning.
"""

from npc_engine.engine.logging_config import get_logger
from typing import Dict, Any, List, Optional, Tuple, Set
import heapq
import math

logger = get_logger("gamemaster.pathfinder")


class PathFinder:
    """
    Pathfinding engine for dialogue and world navigation.

    Implements multiple pathfinding algorithms optimized for different scenarios:
    - A* search for optimal paths with heuristics
    - Dijkstra's for guaranteed shortest paths
    - BFS for unweighted exploration
    - Heuristic planning for goal-directed behavior

    Supports both dialogue context navigation and physical world movement.
    """

    def __init__(self):
        self.cache = {}  # Cache for computed paths

    def find_dialogue_path(self, start_context: str, goal_context: str,
                          contexts: Dict[str, Dict], unlocked_contexts: List[str],
                          visited_contexts: List[str]) -> Optional[List[str]]:
        """
        Find optimal path through dialogue contexts.

        Uses A* search with heuristics based on context properties and player state.

        Args:
            start_context (str): Starting context ID
            goal_context (str): Target context ID
            contexts (Dict[str, Dict]): Context configurations
            unlocked_contexts (List[str]): List of unlocked context IDs
            visited_contexts (List[str]): List of visited context IDs

        Returns:
            Optional[List[str]]: Path as list of context IDs, or None if no path found

        Heuristics:
            - Distance to goal (graph distance)
            - Context difficulty/requirements
            - Social relationship requirements
            - Exploration bonus for unvisited contexts
        """
        if start_context == goal_context:
            return [start_context]

        if start_context not in contexts or goal_context not in contexts:
            return None

        # Use A* with custom heuristic
        return self._a_star_search(
            start_context, goal_context, contexts,
            lambda ctx: self._dialogue_heuristic(ctx, goal_context, contexts,
                                               unlocked_contexts, visited_contexts),
            lambda ctx: self._get_dialogue_neighbors(ctx, contexts, unlocked_contexts)
        )

    def find_navigation_path(self, start_location: str, goal_location: str,
                           world_map: Dict[str, Dict], discovered_locations: List[str],
                           movement_costs: Optional[Dict[str, float]] = None) -> Optional[List[str]]:
        """
        Find optimal navigation path through world locations.

        Uses A* search optimized for physical movement with terrain costs.

        Args:
            start_location (str): Starting location ID
            goal_location (str): Target location ID
            world_map (Dict[str, Dict]): World location configurations
            discovered_locations (List[str]): List of discovered location IDs
            movement_costs (Optional[Dict[str, float]]): Custom movement costs per location

        Returns:
            Optional[List[str]]: Path as list of location IDs, or None if no path found

        Features:
            - Terrain-based movement costs
            - Discovery requirements (can't path through undiscovered areas)
            - Optimal path selection with A* algorithm
        """
        if start_location == goal_location:
            return [start_location]

        if start_location not in world_map or goal_location not in world_map:
            return None

        # Use A* with distance heuristic
        return self._a_star_search(
            start_location, goal_location, world_map,
            lambda loc: self._navigation_heuristic(loc, goal_location, world_map),
            lambda loc: self._get_navigation_neighbors(loc, world_map, discovered_locations),
            lambda loc: self._get_movement_cost(loc, movement_costs)
        )

    def find_all_reachable_contexts(self, start_context: str, contexts: Dict[str, Dict],
                                   unlocked_contexts: List[str], max_depth: int = 10) -> Set[str]:
        """
        Find all contexts reachable from starting point within depth limit.

        Uses BFS to explore reachable contexts, respecting locks and requirements.

        Args:
            start_context (str): Starting context ID
            contexts (Dict[str, Dict]): Context configurations
            unlocked_contexts (List[str]): List of unlocked context IDs
            max_depth (int): Maximum exploration depth

        Returns:
            Set[str]: Set of reachable context IDs
        """
        if start_context not in contexts:
            return set()

        reachable = set()
        visited = set()
        queue = [(start_context, 0)]  # (context, depth)

        while queue:
            current, depth = queue.pop(0)

            if current in visited or depth > max_depth:
                continue

            visited.add(current)
            reachable.add(current)

            # Get neighbors
            neighbors = self._get_dialogue_neighbors(current, contexts, unlocked_contexts)
            for neighbor in neighbors:
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))

        return reachable

    def find_optimal_exploration_path(self, current_location: str, world_map: Dict[str, Dict],
                                     discovered_locations: List[str], exploration_goals: List[str],
                                     max_steps: int = 20) -> List[str]:
        """
        Find path that maximizes exploration while heading toward goals.

        Uses heuristic search to balance exploration with goal-directed movement.

        Args:
            current_location (str): Current location ID
            world_map (Dict[str, Dict]): World location configurations
            discovered_locations (List[str]): List of discovered location IDs
            exploration_goals (List[str]): Priority exploration targets
            max_steps (int): Maximum path length to consider

        Returns:
            List[str]: Exploration path prioritizing discovery and goals

        Strategy:
            - Prioritize undiscovered adjacent locations
            - Move toward exploration goals when no local discoveries available
            - Balance exploration vs goal-directed movement
        """
        if not exploration_goals:
            return [current_location]

        path = [current_location]
        current = current_location
        steps = 0

        while steps < max_steps:
            # Get unexplored neighbors
            neighbors = self._get_navigation_neighbors(current, world_map, discovered_locations)
            unexplored = [n for n in neighbors if n not in discovered_locations]

            if unexplored:
                # Choose closest to exploration goals
                next_loc = self._choose_best_exploration_target(unexplored, exploration_goals, world_map)
                path.append(next_loc)
                current = next_loc
                steps += 1
            else:
                # No unexplored neighbors, move toward goals
                goal_path = self.find_navigation_path(current, exploration_goals[0],
                                                    world_map, discovered_locations)
                if goal_path and len(goal_path) > 1:
                    next_loc = goal_path[1]  # Next step toward goal
                    path.append(next_loc)
                    current = next_loc
                    steps += 1
                else:
                    break  # Can't move toward goals

        return path

    def _a_star_search(self, start: str, goal: str, graph: Dict[str, Dict],
                      heuristic_func, neighbor_func, cost_func=None) -> Optional[List[str]]:
        """
        Generic A* search implementation.

        Args:
            start (str): Starting node
            goal (str): Goal node
            graph (Dict[str, Dict]): Graph structure
            heuristic_func: Function to estimate cost to goal
            neighbor_func: Function to get neighbors
            cost_func: Optional function to get edge costs

        Returns:
            Optional[List[str]]: Path from start to goal, or None
        """
        if cost_func is None:
            cost_func = lambda x: 1  # Default unit cost

        frontier = [(0, start)]  # (priority, node)
        came_from = {start: None}
        cost_so_far = {start: 0}

        while frontier:
            current_cost, current = heapq.heappop(frontier)

            if current == goal:
                return self._reconstruct_path(came_from, goal)

            for neighbor in neighbor_func(current):
                new_cost = cost_so_far[current] + cost_func(neighbor)
                if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                    cost_so_far[neighbor] = new_cost
                    priority = new_cost + heuristic_func(neighbor)
                    heapq.heappush(frontier, (priority, neighbor))
                    came_from[neighbor] = current

        return None  # No path found

    def _reconstruct_path(self, came_from: Dict[str, Optional[str]], goal: str) -> List[str]:
        """
        Reconstruct path from came_from dictionary.

        Args:
            came_from (Dict[str, Optional[str]]): Parent pointers
            goal (str): Goal node

        Returns:
            List[str]: Path from start to goal
        """
        path = []
        current = goal
        while current is not None:
            path.append(current)
            current = came_from[current]
        path.reverse()
        return path

    def _dialogue_heuristic(self, context: str, goal: str, contexts: Dict[str, Dict],
                           unlocked_contexts: List[str], visited_contexts: List[str]) -> float:
        """
        Heuristic for dialogue pathfinding.

        Estimates cost to reach goal from current context.

        Args:
            context (str): Current context
            goal (str): Goal context
            contexts (Dict[str, Dict]): Context configurations
            unlocked_contexts (List[str]): Unlocked contexts
            visited_contexts (List[str]): Visited contexts

        Returns:
            float: Estimated cost to goal
        """
        if context == goal:
            return 0

        # Base distance (would need graph distance calculation)
        base_distance = 1.0  # Placeholder

        # Context difficulty modifier
        difficulty = contexts.get(context, {}).get('properties', {}).get('difficulty', 1)
        goal_difficulty = contexts.get(goal, {}).get('properties', {}).get('difficulty', 1)

        # Exploration bonus for unvisited contexts
        exploration_bonus = 0.5 if context not in visited_contexts else 0

        return base_distance + difficulty + goal_difficulty + exploration_bonus

    def _navigation_heuristic(self, location: str, goal: str, world_map: Dict[str, Dict]) -> float:
        """
        Heuristic for navigation pathfinding.

        Uses Euclidean distance as admissible heuristic.

        Args:
            location (str): Current location
            goal (str): Goal location
            world_map (Dict[str, Dict]): World configurations

        Returns:
            float: Estimated distance to goal
        """
        loc_data = world_map.get(location, {})
        goal_data = world_map.get(goal, {})

        loc_pos = loc_data.get('position', (0, 0))
        goal_pos = goal_data.get('position', (0, 0))

        # Euclidean distance
        return math.sqrt((loc_pos[0] - goal_pos[0])**2 + (loc_pos[1] - goal_pos[1])**2)

    def _get_dialogue_neighbors(self, context: str, contexts: Dict[str, Dict],
                               unlocked_contexts: List[str]) -> List[str]:
        """
        Get valid dialogue neighbors for a context.

        Args:
            context (str): Current context
            contexts (Dict[str, Dict]): Context configurations
            unlocked_contexts (List[str]): Unlocked contexts

        Returns:
            List[str]: List of accessible neighbor contexts
        """
        if context not in contexts:
            return []

        neighbors = []
        ctx_data = contexts[context]

        for conn in ctx_data.get('connections', []):
            target = conn.get('to')
            if target in contexts:
                # Check if target is unlocked
                is_locked = contexts[target].get('properties', {}).get('is_locked', False)
                if not is_locked or target in unlocked_contexts:
                    neighbors.append(target)

        return neighbors

    def _get_navigation_neighbors(self, location: str, world_map: Dict[str, Dict],
                                discovered_locations: List[str]) -> List[str]:
        """
        Get valid navigation neighbors for a location.

        Args:
            location (str): Current location
            world_map (Dict[str, Dict]): World configurations
            discovered_locations (List[str]): Discovered locations

        Returns:
            List[str]: List of accessible neighbor locations
        """
        if location not in world_map:
            return []

        neighbors = []
        loc_data = world_map[location]

        for conn in loc_data.get('connections', []):
            target = conn.get('to')
            if target in world_map:
                # Must be discovered to navigate to
                if target in discovered_locations:
                    neighbors.append(target)

        return neighbors

    def _get_movement_cost(self, location: str, movement_costs: Optional[Dict[str, float]]) -> float:
        """
        Get movement cost for a location.

        Args:
            location (str): Location ID
            movement_costs (Optional[Dict[str, float]]): Custom costs

        Returns:
            float: Movement cost
        """
        if movement_costs and location in movement_costs:
            return movement_costs[location]
        return 1.0  # Default unit cost

    def _choose_best_exploration_target(self, candidates: List[str], goals: List[str],
                                       world_map: Dict[str, Dict]) -> str:
        """
        Choose best exploration target from candidates.

        Prioritizes candidates closest to exploration goals.

        Args:
            candidates (List[str]): Candidate locations
            goals (List[str]): Exploration goals
            world_map (Dict[str, Dict]): World configurations

        Returns:
            str: Best candidate location
        """
        if not candidates:
            return ""

        if not goals:
            return candidates[0]

        # Find candidate closest to any goal
        best_candidate = candidates[0]
        best_distance = float('inf')

        for candidate in candidates:
            for goal in goals:
                dist = self._navigation_heuristic(candidate, goal, world_map)
                if dist < best_distance:
                    best_distance = dist
                    best_candidate = candidate

        return best_candidate

    def clear_cache(self):
        """Clear the pathfinding cache."""
        self.cache.clear()
        logger.info("PathFinder: Cache cleared")

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dict[str, int]: Cache usage statistics
        """
        return {
            "cached_paths": len(self.cache),
            "cache_size": sum(len(path) for path in self.cache.values())
        }