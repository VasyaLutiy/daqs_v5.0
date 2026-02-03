import yaml
from pathlib import Path
from typing import Dict, List, Optional, cast
from .graph import WorldGraph, WorldNode, NodeType, LocationNode, ItemNode, NPCNode, Edge, EdgeType, Condition

def load_yaml_file(path: Path) -> dict:
    """Load YAML file."""
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def resolve_containments(world: WorldGraph, all_raw_nodes: Dict[str, WorldNode]):
    """Resolve containment references."""
    for loc_id, loc in world.locations.items():
        for item_id in loc.contained_items:
            if item_id in world.items:
                loc.items[item_id] = world.items[item_id]
        for obj_id in loc.contained_objects:
            if obj_id in world.objects:
                loc.objects[obj_id] = world.objects[obj_id]
        for npc_id in loc.contained_npcs:
            if npc_id in world.npcs:
                loc.npcs[npc_id] = world.npcs[npc_id]

def create_node_from_data(data: dict) -> WorldNode:
    """Factory to create a specific node type from data dictionary."""
    node_id = data["id"]
    node_type_str = data.get("type", "object").lower()
    node_type = NodeType(node_type_str)
    
    base_kwargs = {
        "id": node_id,
        "type": node_type,
        "name": data.get("name", node_id),
        "description": data.get("description", ""),
        "properties": data.get("properties", {}),
    }
    
    if node_type == NodeType.LOCATION:
        return LocationNode(
            **base_kwargs,
            region=data.get("region"),
            contained_items=data.get("contained_items", []),
            contained_objects=data.get("contained_objects", []),
            contained_npcs=data.get("contained_npcs", []),
        )
    elif node_type == NodeType.ITEM:
        return ItemNode(**base_kwargs)
    elif node_type == NodeType.NPC:
        node = NPCNode(
            **base_kwargs,
            personality=data.get("personality"),
            speech_style=data.get("speech_style")
        )
        node.properties["dialogue_quest"] = data.get("dialogue_quest", False)
        node.properties["social_persona"] = data.get("social_persona", "persona_cyber")
        return node
    else:
        return WorldNode(**base_kwargs)

def register_node(world: WorldGraph, node: WorldNode, all_raw_nodes: Dict[str, WorldNode]):
    """Registers a node into the world graph structures."""
    if node.id in all_raw_nodes:
        return 
    all_raw_nodes[node.id] = node
    world.all_nodes[node.id] = node
    if node.type == NodeType.REGION:
        world.regions[node.id] = node
    elif node.type == NodeType.LOCATION:
        loc_node = cast(LocationNode, node)
        world.locations[node.id] = loc_node
        if loc_node.region:
            world.region_to_locations[loc_node.region].append(node.id)
    elif node.type == NodeType.ITEM:
        world.items[node.id] = cast(ItemNode, node)
    elif node.type == NodeType.NPC:
        world.npcs[node.id] = cast(NPCNode, node)
    elif node.type == NodeType.OBJECT:
        world.objects[node.id] = cast(WorldNode, node)

def _process_contains(world: WorldGraph, parent_node: WorldNode, data: dict, all_raw_nodes: Dict[str, WorldNode], raw_data: Dict[str, dict]):
    """Recursively processes the 'contains' section of a node."""
    contains = data.get("contains", {})
    if not contains: return
    
    for category, items in contains.items():
        child_type = "object"
        if category == "npcs": child_type = "npc"
        elif category == "items": child_type = "item"
        
        for child_data in items:
            if "id" not in child_data: continue
            child_data["type"] = child_type
            child_node = create_node_from_data(child_data)
            register_node(world, child_node, all_raw_nodes) # Ensure child is registered globally
            raw_data[child_node.id] = child_data
            
            if isinstance(parent_node, LocationNode):
                if child_type == "npc": parent_node.contained_npcs.append(child_node.id)
                elif child_type == "item": parent_node.contained_items.append(child_node.id)
                elif child_type == "object": 
                    parent_node.contained_objects.append(child_node.id)
                    
                    # --- AUTO-EDGE FOR PORTALS ---
                    props = child_data.get("properties", {})
                    if props.get("is_portal"):
                        target = props.get("target_location")
                        if target:
                            # Create a virtual edge for navigation/oracle
                            edge = Edge(
                                from_node=parent_node.id,
                                to_node=target,
                                edge_type=EdgeType.PORTAL,
                                bidirectional=props.get("bidirectional", False),
                                properties=props
                            )
                            world.edges.append(edge)
                            # Handle bidirectional portals
                            if edge.bidirectional:
                                world.edges.append(Edge(from_node=target, to_node=parent_node.id, edge_type=EdgeType.PORTAL, bidirectional=True, properties=props))

def load_world_from_flat_yaml(world_dir: Path) -> WorldGraph:
    """Load WorldGraph from flat or hierarchical regional YAML architecture."""
    meta_path = world_dir / "meta.yaml"
    meta = load_yaml_file(meta_path)
    
    world = WorldGraph(
        world_id=meta.get("world_id", "unknown_world"),
        name=meta.get("name", "Unknown World"),
        description=meta.get("description", ""),
        quest_chains=meta.get("quest_chains", {}),
        abilities=meta.get("abilities", {}),
    )
    
    nodes_dir = world_dir / "nodes"
    all_raw_nodes: Dict[str, WorldNode] = {}
    raw_data: Dict[str, dict] = {}
    
    for yaml_path in sorted(nodes_dir.rglob("*.yaml")):
        data = load_yaml_file(yaml_path)
        if not data or "id" not in data: continue
            
        main_node = create_node_from_data(data)
        register_node(world, main_node, all_raw_nodes)
        raw_data[main_node.id] = data
        
        # 1. Handle Regional Atlas (Locations inside Region)
        if main_node.type == NodeType.REGION and "locations" in data:
            for loc_data in data["locations"]:
                if "id" not in loc_data: continue
                loc_data["type"] = "location"
                if "region" not in loc_data: loc_data["region"] = main_node.id
                
                loc_node = create_node_from_data(loc_data)
                register_node(world, loc_node, all_raw_nodes)
                raw_data[loc_node.id] = loc_data
                _process_contains(world, loc_node, loc_data, all_raw_nodes, raw_data)

        # 2. Handle Location Atlas (NPCs/Items inside Location)
        _process_contains(world, main_node, data, all_raw_nodes, raw_data)

    resolve_containments(world, all_raw_nodes)
    
    # 3. Add Edges (Must check ALL nodes registered in raw_data)
    for node_id, data in raw_data.items():
        if data.get("type") != "location": continue
        
        for conn in data.get("connections", []):
            to_id = conn.get("to")
            if not to_id or to_id not in world.all_nodes: continue
            
            edge = Edge(
                from_node=node_id,
                to_node=to_id,
                edge_type=EdgeType(conn.get("edge_type", "path")),
                bidirectional=conn.get("bidirectional", False),
                conditions=[Condition.from_yaml(c) for c in conn.get("conditions", [])],
                properties=conn
            )
            world.edges.append(edge)
            if edge.bidirectional:
                reverse_props = conn.copy()
                world.edges.append(Edge(from_node=to_id, to_node=node_id, edge_type=edge.edge_type, bidirectional=True, conditions=edge.conditions, properties=reverse_props))
    
    # Final pass: Ensure all contained items are registered in world.items for quest generation
    for loc_node in world.locations.values():
        for item_id in loc_node.contained_items:
            if item_id in world.all_nodes and item_id not in world.items:
                world.items[item_id] = cast(ItemNode, world.all_nodes[item_id])
    
    return world
