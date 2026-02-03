import streamlit as st
import sys
from pathlib import Path
import requests

# Path setup
sys.path.insert(0, str(Path(__file__).parent))

from gamemaster.engine_core import GameEngine

# --- Config ---
CONFIG_DIR = Path("npc_engine/config/social_world")
API_URL = "http://localhost:8000/process"

st.set_page_config(page_title="DAQS World Builder & QA", page_icon="🏗️", layout="wide")

# --- Logic ---
if "engine" not in st.session_state:
    st.session_state.engine = GameEngine(CONFIG_DIR)

engine = st.session_state.engine

# --- UI ---
st.title("🏗️ DAQS World Builder & Validator")
st.caption("Neuro-Symbolic Level Design Tool")

# Sidebar: Controls
with st.sidebar:
    st.header("🛠 Controls")
    if st.button("♻️ Reload World Data"):
        engine.reload()
        st.success("World reloaded!")
    
    st.divider()
    
    all_locs = list(engine.cache["world_map"].keys())
    
    start_loc = st.selectbox("🚩 Start Location", all_locs, index=0 if all_locs else 0)
    target_loc = st.selectbox("🎯 Target Goal", all_locs, index=len(all_locs)-1 if all_locs else 0)

# Main Area: Split into Visualization and Validation
col_viz, col_qa = st.columns([0.6, 0.4])

with col_viz:
    st.subheader("🗺️ World Topology")
    # Render FULL MAP for the designer with target highlighting
    w_graph = engine.render_world_graph(start_loc, all_locs, full_map=True, target_node=target_loc)
    st.graphviz_chart(w_graph)

with col_qa:
    st.subheader("🔮 Oracle Analysis")
    
    if start_loc and target_loc:
        with st.status("Analyzing path...", expanded=True) as status:
            # 1. Oracle BFS Pathfinding (Returns tuple: reqs, nodes)
            oracle_res = engine.get_path_requirements(start_loc, target_loc, map_key="world_map")
            
            if start_loc == target_loc:
                st.info("Start and Target are the same.")
            elif oracle_res is None:
                # Path is physically impossible
                st.error("❌ No physical path found in graph!")
            else:
                reqs, path_nodes = oracle_res
                st.success("✅ Path exists in topology.")
                if reqs:
                    st.write("**Required Keys to reach destination:**")
                    for r in set(reqs):
                        st.code(f"🔑 {r}", language="python")
                else:
                    st.write("🔓 Path is open (No locks detected).")
                
                with st.expander("Show Oracle Plan (Topological)"):
                    for i, node in enumerate(path_nodes):
                        st.text(f"{i+1}. {node}")
            
            # 2. PDDL Planner Validation (Hard QA)
            st.divider()
            st.write("#### 🧠 PDDL Brain Validation")
            if st.button("Run Formal PDDL Check"):
                # Use consistent ID
                test_player_id = "player_001"
                
                # Construct dummy player data for validation
                dummy_player = {
                    "id": test_player_id,
                    "location": start_loc,
                    "goal": f"(at {test_player_id} {target_loc})", 
                    "abilities": {"stealth": 1, "combat": 1},
                    "inventory": {},
                    "knowledge": {"discovered_locations": all_locs, "visited_locations": []}
                }
                
                print(f"DEBUG: Sending PDDL check for {start_loc} -> {target_loc}")
                
                try:
                    res = requests.post(API_URL, json={"input_json": dummy_player, "oracle_mode": True}, timeout=10)
                    data = res.json()
                    
                    if data.get("status") == "success":
                        st.success(f"🔥 PDDL VALIDATED: Plan found ({len(data['plan'])} steps)")
                        with st.expander("Show Formal Plan"):
                            for step in data['plan']: st.text(step)
                    else:
                        st.error(f"🚫 PDDL FAILED: {data.get('error')}")
                        st.warning("Logic barrier detected. The player is physically blocked.")
                except Exception as e:
                    st.error(f"API Error: {e}. Is the server running?")

st.divider()
# --- Inspector Area ---
st.subheader("🔍 Node Inspector")
selected_node = st.selectbox("Select node to inspect:", all_locs)
if selected_node:
    node_data = engine.cache["world_map"].get(selected_node, {})
    st.json(node_data)
