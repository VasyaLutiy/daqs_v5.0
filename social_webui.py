import streamlit as st
import sys
import json
import requests
from pathlib import Path

# Path setup
sys.path.insert(0, str(Path(__file__).parent))

# Config directory
CONFIG_DIR = Path("npc_engine/config")

# Initialize Logging
from npc_engine.engine.logging_config import logging_manager
logging_manager.setup_all_loggers()

from npc_engine.engine.world.social_pddl_gen import SocialPDDLGenerator
from npc_engine.engine.master.planner import MasterPlanner
from npc_engine.engine.world.player_state import PlayerState
from gamemaster import social_llm
from gamemaster.prompt_orchestrator import orchestrator
from gamemaster.engine_core import GameEngine
from npc_engine.engine.master.pddl_orchestrator import PDDLOrchestrator
from npc_engine.engine.master.hooks.registry import execute_hook
from npc_engine.main_fast import load_player_from_json_data, load_world

# Import our modules
from npc_engine.engine.webui.social_web_libs import analyze_quest_difficulty, save_player_state, sync_world, API_URL, PLAYER_STATE_FILE
from npc_engine.engine.webui.social_web_handle import handle_input
from npc_engine.engine.webui.social_web_render import render_sidebar, render_right_column, render_chat

st.set_page_config(page_title="DAQS v5.0: Unified World", page_icon="🌍", layout="wide")

# --- INITIALIZATION FUNCTIONS ---
def init_session_state():
    """Initialize all session state variables."""
    if "engine" not in st.session_state:
        st.session_state.engine = GameEngine(CONFIG_DIR)

    if "game_mode" not in st.session_state:
        st.session_state.game_mode = "WORLD"  # WORLD | SOCIAL

    if "player_data" not in st.session_state:
        default_data = {
            "id": "player_001",
            "location": "forest_entrance",
            "inventory": {"items": {}},
            "knowledge": {"discovered_locations": ["forest_entrance"], "visited_locations": ["forest_entrance"]}
        }
        
        if PLAYER_STATE_FILE.exists():
            try:
                with open(PLAYER_STATE_FILE, 'r') as f:
                    data = json.load(f)
                    # Defensive init for knowledge lists
                    if "knowledge" not in data: data["knowledge"] = {}
                    if "discovered_locations" not in data["knowledge"]: data["knowledge"]["discovered_locations"] = []
                    if "visited_locations" not in data["knowledge"]: data["knowledge"]["visited_locations"] = []
                    st.session_state.player_data = data
            except Exception as e:
                st.error(f"Error loading player state: {e}")
                st.session_state.player_data = default_data
        else:
            st.warning("Player state file missing. Initializing new game.")
            st.session_state.player_data = default_data
            save_player_state(default_data)

    if "world_cache" not in st.session_state:
        st.session_state.world_cache = {}

    if "world_messages" not in st.session_state:
        st.session_state.world_messages = []  # History for World Mode

    if "social_messages" not in st.session_state:
        st.session_state.social_messages = []  # History for Social Mode

    if "social_state" not in st.session_state:
        # State for the Dialogue Engine
        st.session_state.social_state = {
            "current_context": "ctx_intro",
            "active_persona": "persona_cyber",
            "current_mood": "neutral",
            "concepts": [],
            "visited_contexts": ["ctx_intro"],
            "unlocked_contexts": [],
            "exhausted_triggers": [],
            "shared_items": [],
            "rapport": False,
            "known_facts": []
        }

    # VISUAL MODE FLAG
    if "visual_enabled" not in st.session_state:
        st.session_state.visual_enabled = "--visual" in sys.argv

# Initialize session state
init_session_state()

# --- UI ---
render_sidebar()

# 2. MAIN SPLIT
col_chat, col_right = st.columns([0.65, 0.35])

# --- RIGHT COLUMN (GAME DECK) ---
with col_right:
    render_right_column()

# --- LEFT COLUMN (CHAT / NARRATIVE) ---
with col_chat:
    render_chat()
    
    # INPUT AREA
    prompt = st.chat_input("Your Action...")
    
    if prompt:
        handle_input(prompt)
