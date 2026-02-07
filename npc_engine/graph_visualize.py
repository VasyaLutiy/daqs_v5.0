import sys
from pathlib import Path
import yaml
from engine.world.graph import WorldGraph, WorldNode, NodeType, LocationNode, ItemNode, NPCNode, Edge, EdgeType, Condition
from engine.world.loader import load_world_from_flat_yaml



# === Mermaid ===
def graph_to_mermaid(world: WorldGraph) -> str:
    lines = ["graph TD"]
    
    # Define classes for different link types
    lines.append("    classDef pathClass stroke:#00ff00,stroke-width:2px")  # Green for paths
    lines.append("    classDef containsClass stroke:#0000ff,stroke-dasharray: 5 5")  # Blue dashed for contains
    lines.append("    classDef linkClass stroke:#ff0000,stroke-width:3px")  # Red for links
    lines.append("    classDef hasClass stroke:#ffa500,stroke-dasharray: 10 5")  # Orange dashed for has
    
    # Define classes for node types
    lines.append("    classDef locationClass stroke:#00ff00,stroke-width:2px")  # Light blue for locations
    lines.append("    classDef itemClass stroke:#0000ff,stroke-dasharray: 5 5")  # Light green for items
    lines.append("    classDef npcClass stroke:#ff0000,stroke-width:3px")  # Light pink for NPCs
    lines.append("    classDef objectClass stroke:#ffa500,stroke-dasharray: 10 5")  # Plum for objects
    
    link_index = 0
    path_indices = []
    contains_indices = []
    link_indices = []
    has_indices = []

    for region_id, region in world.regions.items():
        region_name = region.name or region_id
        lines.append(f'    subgraph {region_id}["{region_name}"]')

        for loc_id in world.region_to_locations.get(region_id, []):
            loc = world.locations.get(loc_id)
            if not loc:
                continue
            loc_name = loc.name or loc_id
            lines.append(f'        {loc_id}("{loc_name}"):::locationClass')

            for item_id, item in loc.items.items():
                name = item.name or item_id
                lines.append(f'        {item_id}("{name}"):::itemClass')
                lines.append(f'        {loc_id} -. contains .-> {item_id}')
                contains_indices.append(link_index)
                link_index += 1

            for npc_id, npc in loc.npcs.items():
                name = npc.name or npc_id
                lines.append(f'        {npc_id}[["{name}"]]:::npcClass')
                lines.append(f'        {loc_id} -. contains .-> {npc_id}')
                contains_indices.append(link_index)
                link_index += 1

            for obj_id, obj in loc.objects.items():
                name = obj.name or obj_id
                lines.append(f'        {obj_id}{{"{name}"}}:::objectClass')
                lines.append(f'        {loc_id} -. contains .-> {obj_id}')
                contains_indices.append(link_index)
                link_index += 1

        lines.append("    end")

    for edge in world.edges:
        direction = "<-->" if edge.bidirectional else "-->"
        label = edge.edge_type.value
        lines.append(f'    {edge.from_node} {direction}|{label}| {edge.to_node}')
        path_indices.append(link_index)
        link_index += 1

    # Add links for items with linked_object
    for item in world.items.values():
        linked = item.properties.get('linked_object')
        if linked:
            lines.append(f'    {item.id} -->|linked| {linked}')
            link_indices.append(link_index)
            link_index += 1
        linked_npcs = item.properties.get('linked_npcs', [])
        for npc_id in linked_npcs:
            lines.append(f'    {item.id} -->|linked| {npc_id}')
            link_indices.append(link_index)
            link_index += 1

    # Add has links for NPCs
    for npc in world.npcs.values():
        has_items = npc.properties.get('has_items', [])
        for item_id in has_items:
            lines.append(f'    {npc.id} -. has .-> {item_id}')
            has_indices.append(link_index)
            link_index += 1

    # Apply link styles
    for idx in path_indices:
        lines.append(f"    linkStyle {idx} stroke:#00ff00,stroke-width:2px")
    for idx in contains_indices:
        lines.append(f"    linkStyle {idx} stroke:#0000ff,stroke-dasharray: 5 5")
    for idx in link_indices:
        lines.append(f"    linkStyle {idx} stroke:#ff0000,stroke-width:3px")
    for idx in has_indices:
        lines.append(f"    linkStyle {idx} stroke:#ffa500,stroke-dasharray: 10 5")

    return "\n".join(lines)

def main():
    world_path = Path("config/world/")
    world = load_world_from_flat_yaml(world_path)
    mermaid_code = graph_to_mermaid(world)
    with open("../generated/world_graph.md", "w", encoding="utf-8") as f:
        f.write(mermaid_code)
    print("Mermaid graph saved to generated/world_graph.mmd")
    print("\nPreview:")
    print(mermaid_code)

if __name__ == "__main__":
    main()