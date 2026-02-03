"""
Graph Renderer for DAQS Game Engine

Handles visualization of dialogue contexts and world maps using GraphViz.
Creates interactive graphs showing conversation flows and navigation paths.
"""

from npc_engine.engine.logging_config import get_logger
from typing import Dict, Any, Optional
import graphviz

logger = get_logger("gamemaster.graph")


class GraphRenderer:
    """
    Renders dialogue and world graphs using GraphViz.

    Creates visual representations of conversation flows, context relationships,
    and world navigation. Supports highlighting current state, locked/unlocked
    contexts, and target goals.

    Graph Types:
        - Dialogue graphs: Social conversation contexts
        - World graphs: Physical location navigation
        - State highlighting: Current position, targets, locks
    """

    def render_dialogue_graph(self, state: Dict[str, Any], target_goal: Optional[str] = None, cache: Optional[Dict[str, Dict]] = None) -> graphviz.Digraph:
        """
        Render the dialogue context graph with persona filtering.
        """
        dot = graphviz.Digraph()
        self._configure_graph_style(dot)

        # Extract state information
        current_ctx = state.get("current_context")
        active_persona = state.get("active_persona")
        unlocked_list = state.get("unlocked_contexts", [])
        visited_list = state.get("visited_contexts", [])

        # Get all contexts from cache
        all_contexts = self._get_contexts_from_cache(cache)
        
        # FILTER: Identify which contexts belong to this persona
        relevant_contexts = {}
        if active_persona and cache and "personas" in cache:
            persona_data = cache["personas"].get(active_persona, {})
            persona_ctx_ids = [c['id'] for c in persona_data.get("contexts", [])]
            
            # Add contexts that are explicitly in the persona
            for cid in persona_ctx_ids:
                if cid in all_contexts:
                    relevant_contexts[cid] = all_contexts[cid]
            
            # Safety: always include current context even if not in persona (e.g. global)
            if current_ctx and current_ctx not in relevant_contexts and current_ctx in all_contexts:
                relevant_contexts[current_ctx] = all_contexts[current_ctx]
        else:
            # Fallback: show everything if no persona active
            relevant_contexts = all_contexts

        # Render filtered nodes
        for ctx_id, ctx_data in relevant_contexts.items():
            self._render_context_node(dot, ctx_id, ctx_data, current_ctx,
                                    target_goal, unlocked_list, visited_list)

        # Add edges (only between filtered nodes)
        self._render_context_edges(dot, relevant_contexts)

        return dot

    def render_world_graph(self, current_loc: str, discovered_list: list,
                          full_map: bool = False, target_node: str = None, cache: Optional[Dict[str, Dict]] = None) -> graphviz.Digraph:
        """
        Render the world navigation graph.

        Shows physical locations and navigation paths with exploration state.

        Args:
            current_loc (str): Current location ID
            discovered_list (list): List of discovered location IDs
            full_map (bool): Whether to show all locations or just local area
            target_node (str): Target location to highlight
            cache (Optional[Dict[str, Dict]]): Cache containing contexts and world_map

        Returns:
            graphviz.Digraph: Rendered world graph

        Features:
            - Local view: Shows current location and immediate neighbors
            - Full map: Shows all known locations
            - Exploration state: Hidden, discovered, visited locations
            - Navigation paths: Valid movement connections
        """
        dot = graphviz.Digraph()
        self._configure_graph_style(dot, rankdir='LR')

        # Get world locations from cache
        world_map = self._get_world_map_from_cache(cache)

        if not world_map:
            return dot

        # Determine which nodes to draw
        nodes_to_draw = self._select_nodes_to_draw(current_loc, world_map, full_map, discovered_list)

        # Render location nodes
        for loc_id in nodes_to_draw:
            if loc_id not in world_map:
                continue

            loc_data = world_map[loc_id]
            self._render_location_node(dot, loc_id, loc_data, current_loc, target_node,
                                     discovered_list, full_map)

        # Add navigation edges
        self._render_navigation_edges(dot, nodes_to_draw, world_map)

        return dot

    def _configure_graph_style(self, dot: graphviz.Digraph, rankdir: str = 'TB'):
        """
        Configure base graph styling.

        Args:
            dot (graphviz.Digraph): Graph to configure
            rankdir (str): Layout direction ('TB', 'LR', etc.)
        """
        dot.attr(rankdir=rankdir, bgcolor='transparent')
        dot.attr('node', shape='box', style='rounded,filled',
                fontname='Arial', fontsize='10')
        dot.attr('edge', color='#555555')

    def _render_context_node(self, dot: graphviz.Digraph, ctx_id: str, ctx_data: Dict[str, Any],
                           current_ctx: str, target_goal: str, unlocked_list: list,
                           visited_list: list):
        """
        Render a single context node with appropriate styling.

        Args:
            dot (graphviz.Digraph): Graph to add node to
            ctx_id (str): Context ID
            ctx_data (Dict[str, Any]): Context configuration
            current_ctx (str): Current context ID
            target_goal (str): Target goal context ID
            unlocked_list (list): List of unlocked context IDs
            visited_list (list): List of visited context IDs
        """
        try:
            label = ctx_data.get('name', ctx_id)
            fillcolor = '#ffffff'
            penwidth = '1'
            color = '#000000'

            # Determine styling based on state
            is_locked = ctx_data.get('properties', {}).get('is_locked', False)

            if is_locked and ctx_id not in unlocked_list:
                label = f"🔒 {label}"
                fillcolor = '#eeeeee'
                color = '#999999'
            elif ctx_id == current_ctx:
                fillcolor = '#ffcccc'
                penwidth = '2'
                color = '#cc0000'
            elif ctx_id == target_goal:
                label = f"⭐ {label}"
                fillcolor = '#ffffcc'
                penwidth = '2'
            elif ctx_id in visited_list:
                fillcolor = '#e0e0e0'

            dot.node(ctx_id, label, fillcolor=fillcolor, color=color, penwidth=penwidth)

        except Exception as e:
            logger.error(f"Error rendering context node {ctx_id}: {e}")

    def _render_context_edges(self, dot: graphviz.Digraph, contexts: Dict[str, Dict]):
        """
        Render connection edges between contexts.

        Args:
            dot (graphviz.Digraph): Graph to add edges to
            contexts (Dict[str, Dict]): Context configurations
        """
        for ctx_id, ctx_data in contexts.items():
            for conn in ctx_data.get('connections', []):
                target = conn.get('to')
                if target in contexts:
                    direction = conn.get('direction', 'forward')
                    # Could add different edge styles based on direction
                    dot.edge(ctx_id, target)

    def _render_location_node(self, dot: graphviz.Digraph, loc_id: str, loc_data: Dict[str, Any],
                            current_loc: str, target_node: str, discovered_list: list,
                            full_map: bool):
        """
        Render a single location node with exploration state styling.

        Args:
            dot (graphviz.Digraph): Graph to add node to
            loc_id (str): Location ID
            loc_data (Dict[str, Any]): Location configuration
            current_loc (str): Current location ID
            target_node (str): Target location ID
            discovered_list (list): List of discovered location IDs
            full_map (bool): Whether showing full map
        """
        fillcolor = '#ffffff'
        color = '#000000'
        label = loc_data.get('name', loc_id)

        if loc_id == current_loc:
            fillcolor = '#ffcccc'
            color = '#cc0000'
            label = f"📍 {label}"
        elif loc_id == target_node:
            fillcolor = '#ffffcc'
            color = '#ccaa00'
            label = f"⭐ {label}"
        elif not full_map and loc_id not in discovered_list:
            label = "???"
            fillcolor = '#f5f5f5'
            color = '#dddddd'
        elif loc_id in discovered_list:
            fillcolor = '#e1f5fe'

        dot.node(loc_id, label, fillcolor=fillcolor, color=color)

    def _render_navigation_edges(self, dot: graphviz.Digraph, nodes_to_draw: set,
                               world_map: Dict[str, Dict]):
        """
        Render navigation edges between locations.

        Args:
            dot (graphviz.Digraph): Graph to add edges to
            nodes_to_draw (set): Set of location IDs to include
            world_map (Dict[str, Dict]): World location configurations
        """
        for loc_id in nodes_to_draw:
            if loc_id not in world_map:
                continue

            loc_data = world_map[loc_id]
            for conn in loc_data.get('connections', []):
                target = conn.get('to')
                if target in nodes_to_draw:
                    dot.edge(loc_id, target)

    def _select_nodes_to_draw(self, current_loc: str, world_map: Dict[str, Dict],
                            full_map: bool, discovered_list: list) -> set:
        """
        Determine which location nodes to include in the graph.

        Args:
            current_loc (str): Current location ID
            world_map (Dict[str, Dict]): World location configurations
            full_map (bool): Whether to show all locations
            discovered_list (list): List of discovered location IDs

        Returns:
            set: Set of location IDs to render
        """
        if full_map:
            return set(world_map.keys())

        if current_loc not in world_map:
            return set()

        # Local view: current location + immediate neighbors
        neighbors = set()
        for conn in world_map[current_loc].get('connections', []):
            neighbors.add(conn['to'])

        # Add reverse connections
        for loc_id, loc_data in world_map.items():
            for conn in loc_data.get('connections', []):
                if conn['to'] == current_loc:
                    neighbors.add(loc_id)

        return neighbors | {current_loc}

    def _get_contexts_from_cache(self, cache: Optional[Dict[str, Dict]]) -> Dict[str, Dict]:
        """
        Get contexts from cache.

        Args:
            cache (Optional[Dict[str, Dict]]): Cache containing contexts

        Returns:
            Dict[str, Dict]: Context configurations
        """
        if cache and "contexts" in cache:
            return cache["contexts"]
        return {}

    def _get_world_map_from_cache(self, cache: Optional[Dict[str, Dict]]) -> Dict[str, Dict]:
        """
        Get world map from cache.

        Args:
            cache (Optional[Dict[str, Dict]]): Cache containing world_map

        Returns:
            Dict[str, Dict]: World location configurations
        """
        if cache and "world_map" in cache:
            return cache["world_map"]
        return {}

    def export_graph(self, graph: graphviz.Digraph, format: str = 'png',
                    filename: str = 'graph') -> str:
        """
        Export graph to file in specified format.

        Args:
            graph (graphviz.Digraph): Graph to export
            format (str): Export format ('png', 'svg', 'pdf', etc.)
            filename (str): Output filename (without extension)

        Returns:
            str: Path to exported file
        """
        try:
            output_path = graph.render(filename=filename, format=format,
                                     cleanup=True)
            logger.info(f"GraphRenderer: Exported graph to {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"GraphRenderer: Failed to export graph: {e}")
            return ""

    def get_graph_statistics(self, graph: graphviz.Digraph) -> Dict[str, int]:
        """
        Get statistics about the rendered graph.

        Args:
            graph (graphviz.Digraph): Graph to analyze

        Returns:
            Dict[str, int]: Graph statistics
        """
        # This would require parsing the graphviz source
        # For now, return placeholder stats
        return {
            "nodes": 0,
            "edges": 0,
            "complexity": 0
        }

    def _get_contexts_from_cache(self, cache: Optional[Dict[str, Dict]]) -> Dict[str, Dict]:
        """
        Get contexts from cache.

        Args:
            cache (Optional[Dict[str, Dict]]): Cache containing contexts

        Returns:
            Dict[str, Dict]: Context configurations
        """
        if cache and "contexts" in cache:
            return cache["contexts"]
        return {}

    def _get_world_map_from_cache(self, cache: Optional[Dict[str, Dict]]) -> Dict[str, Dict]:
        """
        Get world map from cache.

        Args:
            cache (Optional[Dict[str, Dict]]): Cache containing world_map

        Returns:
            Dict[str, Dict]: World location configurations
        """
        if cache and "world_map" in cache:
            return cache["world_map"]
        return {}