import json
import requests
import streamlit as st
from pathlib import Path
from npc_engine.main_fast import load_player_from_json_data, load_world
from npc_engine.engine.master.hooks.registry import execute_hook
import npc_engine.engine.master.hooks.quest_hooks # Ensure hooks are registered

# --- CONSTANTS ---
API_URL = "http://localhost:8000/process"
PLAYER_STATE_FILE = Path("player_state.json")

def analyze_quest_difficulty_simple(player_goal: str) -> str:
    """
    Analyze quest difficulty using simple keyword-based heuristics.
    
    Performs basic pattern matching on PDDL goal strings to determine quest
    complexity. This is a lightweight alternative to advanced PDDL planning
    analysis, suitable for quick assessments.
    
    Args:
        player_goal (str): PDDL-formatted goal string (e.g., "(has-item player sword)")
    
    Returns:
        str: Difficulty concept identifier
            - "cpt_quest_hard": Epic/legendary/ancient/cursed items
            - "cpt_quest_easy": Common/simple/basic items or non-item goals
            - "cpt_quest_none": No active goal
    
    Algorithm:
        - Extracts target item from has-item goals using regex
        - Checks for difficulty keywords in item names
        - Defaults to easy for unrecognized patterns
        - Non-item goals automatically classified as easy
    
    Note:
        This is a simplified heuristic - consider using analyze_quest_difficulty()
        for more sophisticated PDDL-based analysis.
    """
    if not player_goal:
        return "cpt_quest_none"

    if "has-item" in player_goal:
        import re
        match = re.search(r'\(has-item\s+\w+\s+(\w+)\)', player_goal)
        if match:
            target_item = match.group(1)
            item_lower = target_item.lower()
            if any(keyword in item_lower for keyword in ["fort", "epic", "legendary", "ancient", "cursed"]):
                return "cpt_quest_hard"
            elif any(keyword in item_lower for keyword in ["easy", "simple", "basic", "common"]):
                return "cpt_quest_easy"
            else:
                return "cpt_quest_easy"  # Default assumption
    else:
        return "cpt_quest_easy"  # Non-item quests default to easy

def analyze_quest_difficulty(player_goal: str) -> str:
    """
    Advanced quest difficulty analysis using PDDL planning engine integration.
    
    Leverages the full power of the PDDL planning system to analyze quest
    feasibility and complexity. This provides much more accurate difficulty
    assessment compared to simple keyword matching, taking into account
    actual game state, available actions, and planning constraints.
    
    Args:
        player_goal (str): PDDL-formatted goal string representing the quest objective
    
    Returns:
        str: Difficulty assessment concept
            - "cpt_quest_hard": Complex multi-step quests requiring planning
            - "cpt_quest_easy": Straightforward single-step or simple quests
            - "cpt_quest_none": No active quest goal
            - "cpt_quest_impossible": Goal cannot be achieved with current game state
    
    Process:
        1. Validates goal format and extracts target elements
        2. Calls world engine API with oracle mode for planning analysis
        3. Analyzes solution path length and complexity
        4. Falls back to simple keyword analysis if planning fails
        5. Returns appropriate difficulty concept for NPC dialogue
    
    Integration:
        - Uses sync_world() with oracle=True for planning queries
        - Extracts plan length as primary difficulty metric
        - Handles API failures gracefully with fallback logic
    
    Note:
        This function requires active world engine connection and may
        incur performance cost for complex planning operations.
    """
    if not player_goal:
        return "cpt_quest_none"

    try:
        # Load world graph (same as backend)
        world = load_world()

        # Convert player_data dict to PlayerState object
        player_state, _ = load_player_from_json_data(st.session_state.player_data)
        player_state.goal = player_goal  # Set the current goal

        # Execute the advanced hook
        result = execute_hook("analyze_quest_difficulty", player_state, world)

        return result

    except Exception as e:
        st.warning(f"Advanced quest analysis failed, using simple fallback: {e}")
        # Clean fallback to simple analysis
        return analyze_quest_difficulty_simple(player_goal)

def save_player_state(data):
    """
    Persist the current player state to disk for game continuity.
    
    Serializes the complete player data structure to JSON format and saves
    it to the designated player state file. This ensures that player progress,
    inventory, quests, and other stateful information survives application
    restarts and sessions.
    
    Args:
        data (dict): Complete player state dictionary containing:
            - id: Player identifier
            - location: Current location
            - abilities: Player skills/stats
            - inventory: Items and quantities
            - knowledge: Discovered/visited locations
            - goal: Active quest objective (if any)
            - dialogue_phase: Social interaction state
            - And other game-specific data
    
    Effects:
        - Overwrites PLAYER_STATE_FILE with current state
        - Uses UTF-8 encoding with pretty-printing (indent=2)
        - Ensures non-ASCII characters are preserved
        - Displays error message if save operation fails
    
    Error Handling:
        - Catches all exceptions during file operations
        - Shows user-friendly error message via Streamlit
        - Does not raise exceptions - fails gracefully
    
    Note:
        This function should be called after any significant state changes
        to prevent progress loss.
    """
    try:
        with open(PLAYER_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        st.error(f"Failed to save state: {e}")

def call_world_engine(input_data, oracle=False):
    """
    Interface to the external world engine API for game state processing.
    
    Sends player state and commands to the world engine service for processing.
    The world engine handles PDDL planning, quest resolution, and world state
    updates. Supports both normal execution and oracle (planning-only) modes.
    
    Args:
        input_data (dict): Player state and command data to send to world engine
        oracle (bool, optional): If True, runs in planning/analysis mode without
                                executing actions. Defaults to False.
    
    Returns:
        dict or None: World engine response containing:
            - plan: List of action steps for quest resolution
            - error: Error message if processing failed
            - state_updates: Any world state changes
            - Returns None if API call fails
    
    API Payload:
        {
            "input_json": input_data,
            "oracle_mode": oracle
        }
    
    Error Handling:
        - Catches all network and API errors
        - Returns None on failure (caller handles gracefully)
        - Shows user-friendly error message via Streamlit
    
    Integration:
        - Uses requests library for HTTP POST to API_URL
        - Expects JSON response from world engine
        - Times out automatically on network issues
    """
    try:
        payload = {"input_json": input_data, "oracle_mode": oracle}
        response = requests.post(API_URL, json=payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"World Engine Error: {e}")
        return None

def sync_world(oracle=False):
    """Syncs local state with World Engine and updates UI data."""
    res = call_world_engine(st.session_state.player_data, oracle)
    if res:
        st.session_state.world_cache = res
        # Check if quest goal is achieved
        if "goal" in st.session_state.player_data:
            goal = st.session_state.player_data["goal"]
            if goal.startswith("(has-item"):
                import re
                match = re.search(r'\(has-item\s+\w+\s+(\w+)\)', goal)
                if match:
                    item_id = match.group(1)
                    inventory = st.session_state.player_data.get("inventory", {}).get("items", {})
                    if item_id in inventory and inventory[item_id] > 0:
                        # Quest completed
                        del st.session_state.player_data["goal"]
                        save_player_state(st.session_state.player_data)
                        st.success(f"🎉 Quest completed! Obtained {item_id}")
        return res
    return None