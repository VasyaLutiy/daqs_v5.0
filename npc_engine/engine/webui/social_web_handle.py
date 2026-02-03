import streamlit as st
from pathlib import Path
from npc_engine.engine.master.pddl_orchestrator import PDDLOrchestrator
from gamemaster import social_llm
from gamemaster.prompt_orchestrator import orchestrator
from gamemaster.visual_generator import VisualGenerator
from npc_engine.main_fast import load_world
from .social_web_libs import sync_world, save_player_state, analyze_quest_difficulty, call_world_engine

def handle_npc_interaction(npc, can_quest, current_location):
    """
    Initiate social interaction with an NPC, transitioning to SOCIAL game mode.
    
    Refactored to be Data-Driven using Persona Properties.
    """
    # TRIGGER SOCIAL MODE
    st.session_state.game_mode = "SOCIAL"
    
    # CRITICAL FIX: Use the explicitly passed location (Source of Truth)
    st.session_state.player_data["location"] = current_location
    save_player_state(st.session_state.player_data) # Persist fix
    
    # 1. Determine Persona ID
    persona_id = npc.get("social_persona", "persona_cyber")
    st.write(f"Debug: Selected persona: {persona_id}")

    # 2. Dynamic Initialization via PDDL Orchestrator
    pddl_orch = PDDLOrchestrator()
    meta = pddl_orch.get_persona_metadata(persona_id)
    
    properties = meta.get("properties", {})
    start_ctx = meta.get("start_context", "ctx_intro")
    target_goal = meta.get("target_goal", "ctx_core")

    # 3. State Reset Logic
    current_persona = st.session_state.social_state.get("active_persona")
    if current_persona != persona_id:
        # Complete state reset for new persona
        st.session_state.social_state = {
            "current_context": start_ctx,
            "active_persona": persona_id,
            "current_location": current_location, # Use passed location
            "concepts": [],
            "visited_contexts": [start_ctx],
            "unlocked_contexts": [],
            "exhausted_triggers": [],
            "rapport": False,
            "known_facts": []
        }
        st.session_state.social_messages = []  # Clear chat history too

    st.session_state.social_state["active_persona"] = persona_id
    st.session_state.social_state["current_context"] = start_ctx
    st.session_state.social_state["current_location"] = current_location # Ensure update even if persona didn't change
    
    # FORCE UPDATE LOCATION (Fixes 'unknown' location issue)
    st.session_state.social_state["current_location"] = st.session_state.player_data.get("location", "unknown")

    # 4. Behavior: Quest Difficulty Analysis
    # Replaces hardcoded check for Dolores
    # Default is True unless specified otherwise (like for Dolores)
    if can_quest and properties.get("perform_quest_analysis", True):
        current_goal = st.session_state.player_data.get("goal")
        quest_concept = analyze_quest_difficulty(current_goal)
        # Hook for planning logic
        if quest_concept:
             # Add the concept to the active social state
             if quest_concept not in st.session_state.social_state["concepts"]:
                 st.session_state.social_state["concepts"].append(quest_concept)
                 st.write(f"Debug: Added quest concept: {quest_concept}")

    # 5. Behavior: Introduction
    oracle_res = st.session_state.engine.get_path_requirements(
        start_ctx, target_goal, map_key="contexts", state=st.session_state.social_state
    )
    quest_keys = oracle_res[0] if oracle_res else []

    # Replaces "if can_quest and persona_id != 'persona_dolores'"
    # Logic: If persona is "active" on enter (like Megan or generic NPCs), generate intro.
    # If "passive" (like Dolores), clear messages and wait.
    
    # Heuristic fallback: if prop missing, active if quest exists, passive otherwise
    default_behavior = "active" if can_quest else "passive"
    behavior = properties.get("behavior_on_enter", default_behavior)
    
    if behavior == "active":
        intro = social_llm.generate_quest_intro(st.session_state.social_state, quest_keys, target_goal)
        
        # VISUAL GENERATION FOR INTRO
        img_path = None
        # DEBUG DIAGNOSTIC
        print(f"DEBUG: Intro Visual Check. Enabled: {st.session_state.get('visual_enabled')}, Keys: {intro.keys()}")
        
        if st.session_state.get("visual_enabled", False) and "scene_description" in intro:
            try:
                vis_gen = VisualGenerator()
                # Get Readable Names
                p_name = meta.get("persona_name", persona_id)
                p_data = orchestrator.personas_data.get(persona_id, {})
                p_desc = p_data.get("description", "A mysterious figure.")
                
                # Resolve Image Reference Path
                image_ref = p_data.get("properties", {}).get("image_reference")
                image_ref_path = None
                if image_ref:
                    image_ref_path = str(Path("npc_engine/config/social_world/nodes/personas") / image_ref)
                
                # Need location name, not ID. Try world cache or orchestrator lookup?
                # Quickest way: Use orchestrator instance we already have
                loc_id = st.session_state.social_state["current_location"]
                loc_data = orchestrator.locations_data.get(loc_id, {})
                loc_name = loc_data.get("name", loc_id)
                
                with st.spinner("Visualizing scene..."):
                    img_path = vis_gen.generate_scene_visual(
                        intro["scene_description"], 
                        p_name, 
                        p_desc, 
                        loc_name, 
                        image_ref_path=image_ref_path
                    )
            except Exception as e:
                print(f"CRITICAL VISUAL ERROR: {e}") # Print to console to survive rerun
                st.error(f"Visual gen failed. Ref: {image_ref_path}. Error: {e}")

        st.session_state.social_messages = [{"role": "assistant", "content": intro, "image": img_path}]
    else:
        # Passive / Wait for input
        st.session_state.social_messages = []
        st.write(f"Debug: Starting passive interaction with {persona_id}")

    st.rerun()

def handle_navigation(eid):
    """
    Handle player navigation to a new location in the game world.
    
    Updates the player's current location and expands their knowledge of
    discovered and visited locations. This affects what locations appear
    on the world map and what navigation options are available.
    
    Args:
        eid (str): Entity ID of the location to navigate to
    
    Effects:
        - Updates player_data["location"]
        - Adds location to discovered_locations if not already present
        - Adds location to visited_locations
        - Persists changes to player state
    """
    st.session_state.player_data["location"] = eid
    know = st.session_state.player_data.setdefault("knowledge", {})
    disc = know.setdefault("discovered_locations", [])
    visi = know.setdefault("visited_locations", [])
    if eid not in disc: disc.append(eid)
    if eid not in visi: visi.append(eid)

    # VISUAL GENERATION (Fog of War)
    if st.session_state.get("visual_enabled", False):
        try:
            world = load_world()
            loc_node = world.get_node(eid)
            if loc_node:
                vis_gen = VisualGenerator()
                # Generate or Load from Cache
                with st.spinner("Revealing world..."):
                    vis_gen.generate_location_visual(
                        eid,
                        getattr(loc_node, 'name', eid),
                        getattr(loc_node, 'description', 'A mysterious place.'),
                        getattr(loc_node, 'region', 'Fantasy World')
                    )
        except Exception as e:
            st.warning(f"Visual generation skipped: {e}")

    save_player_state(st.session_state.player_data)
    with st.spinner("Syncing..."):
        sync_world(oracle=True)
    st.rerun()

def handle_item_pickup(item):
    """
    Handle pickup of an item from the game world.
    
    Adds the specified item to the player's inventory, incrementing the count
    if the item is already possessed. Updates the player's knowledge of 
    discovered items and syncs with the world engine.
    
    Args:
        item (dict): Item data containing at minimum an 'id' key
    
    Effects:
        - Increments item count in player_data["inventory"]["items"]
        - Updates discovered_items knowledge
        - Persists player state
        - Triggers world sync with oracle mode for consistency
    """
    # Add to inventory
    inv = st.session_state.player_data.setdefault("inventory", {}).setdefault("items", {})
    inv[item['id']] = inv.get(item['id'], 0) + 1
    save_player_state(st.session_state.player_data)
    with st.spinner("Syncing..."):
        sync_world(oracle=True)
    st.rerun()

def handle_leave_conversation():
    """
    Handle the player leaving a social conversation with an NPC.
    
    Transitions back to WORLD exploration mode and cleans up social state.
    Removes any active quest goal since social conversations are complete,
    forcing the player to re-engage quests through proper channels.
    
    Effects:
        - Switches game_mode back to "WORLD"
        - Clears any active quest goal from player_data
        - Persists the updated player state
        - Triggers UI refresh
    """
    st.session_state.game_mode = "WORLD"
    # Reset goal when leaving social mode
    if "goal" in st.session_state.player_data:
        del st.session_state.player_data["goal"]
    save_player_state(st.session_state.player_data)
    st.rerun()

def handle_quest_acceptance(quest_goal, quest_name):
    """
    Handle the formal acceptance of a quest by the player.
    
    This function marks the official start of a quest by setting the goal
    in player data and requesting a solution plan from the world engine.
    The quest becomes active and will influence NPC interactions and
    world state progression.
    
    Args:
        quest_goal (str): PDDL-formatted goal string (e.g., "(has-item player item)")
        quest_name (str): Human-readable quest name for display
    
    Process:
        1. Sets the quest goal in player_data (makes quest active)
        2. Persists the updated player state
        3. Requests solution plan from world engine via API
        4. Generates narrative description of the quest mission
        5. Updates UI with quest acceptance confirmation
    
    Effects:
        - Quest becomes active and influences NPC behavior
        - Player state is persisted to disk
        - World engine generates solution path
        - UI shows quest mission narrative
    """
    # 1. Set Goal for this specific quest
    st.session_state.player_data["goal"] = quest_goal

    # 2. Persist to Disk (Official acceptance start)
    save_player_state(st.session_state.player_data)

    # 3. Get Plan from World Engine
    with st.spinner("Calculating Logistics..."):
        res = sync_world(oracle=True)
        plan = res.get("plan", [])

    # 4. Generate Narrative for this quest
    payload = social_llm.generate_quest_mission(st.session_state.social_state, plan, quest_name)
    st.session_state.social_messages.append({"role": "assistant", "content": payload})
    st.rerun()

def handle_input(prompt):
    """
    Process user input in either WORLD exploration or SOCIAL conversation mode.
    
    This is the main input handler that routes user messages to appropriate
    processing logic based on the current game mode. In WORLD mode, it handles
    navigation and simple actions. In SOCIAL mode, it processes dialogue with
    NPCs using advanced NLU and PDDL planning.
    
    Args:
        prompt (str): The user's input text/message
    
    WORLD Mode Process:
        - Updates player goals based on input
        - Handles movement commands
        - Calls world engine for action resolution
        - Generates narrative responses
    
    SOCIAL Mode Process:
        - Analyzes valid moves using game engine
        - Uses NLU to determine player intent
        - Applies actions to social state
        - Generates NPC dialogue responses
        - Handles NPC-initiated offers/flirts automatically
    
    Effects:
        - Updates appropriate message history
        - Modifies game state based on actions
        - Triggers UI refresh with new content
        - May auto-apply NPC offers when conditions are met
    """
    # User message
    messages = st.session_state.world_messages if st.session_state.game_mode == "WORLD" else st.session_state.social_messages
    messages.append({"role": "user", "content": prompt})

    # --- PROCESS INPUT BASED ON MODE ---

    if st.session_state.game_mode == "WORLD":
        # 1. Update Player Goal/Action
        st.session_state.player_data["goal"] = f"(visited {prompt})" if " " not in prompt else None  # Simple hack for demo
        if "move to" in prompt:
            loc = prompt.replace("move to ", "").strip()
            st.session_state.player_data["location"] = loc

        # 2. Call World Engine
        with st.spinner("Calculating World Physics..."):
            res = call_world_engine(st.session_state.player_data, oracle=True)
            st.session_state.world_cache = res

            # 3. Generate Narrative (Simple fallback for now)
            plan_text = "\n".join(res.get("plan", []))
            narrative = f"**System:** Processing action...\n\nPlan:\n```\n{plan_text}\n```"
            if res.get("error"):
                narrative = f"❌ **Error:** {res['error']}"

            messages.append({"role": "assistant", "content": narrative})
            st.rerun()

    else:  # SOCIAL MODE
        # CRITICAL FIX: Ensure Location Consistency
        # If player_data location is missing/unknown but world_cache has it, sync it up.
        current_loc = st.session_state.player_data.get("location", "unknown")
        if (current_loc == "unknown" or not current_loc) and "world_cache" in st.session_state:
             meta_loc = st.session_state.world_cache.get("metadata", {}).get("location")
             if meta_loc:
                 st.session_state.player_data["location"] = meta_loc
                 save_player_state(st.session_state.player_data)

        orchestrator.reload()
        with st.spinner("Processing Logic..."):
            engine = st.session_state.engine
            state = st.session_state.social_state.copy()  # Make a copy to avoid modifying original
            
            # ENSURE LOCATION IS ALWAYS UP TO DATE
            state["current_location"] = st.session_state.player_data.get("location", "unknown")
            state["player_data"] = st.session_state.player_data  # Add player data for NPC logic

            # 1. Intent
            valid_moves = engine.get_valid_moves(state)
            adapter = {
                "current_topic": state["current_context"],
                "active_persona": state["active_persona"],
                "current_mood": state.get("current_mood", "neutral"),
                "current_location": st.session_state.player_data.get("location", "unknown"), # FIX: Pass location to adapter
                "rapport": False,
                "known_facts": state["concepts"]
            }

            pddl_action = social_llm.get_social_intent(prompt, adapter, valid_moves)

            # 2. Apply
            if pddl_action and pddl_action != "None":
                engine.apply_action(pddl_action, state)
                # CRITICAL: Sync state back to session_state
                st.session_state.social_state = state

            # 3. Narrative
            # Recalculate adapter after state change
            adapter["current_topic"] = state["current_context"]
            adapter["current_mood"] = state.get("current_mood", "neutral")
            adapter["current_location"] = st.session_state.player_data.get("location", "unknown") # Update location too

            # Priority Logic & V2 Integration
            if pddl_action and pddl_action.startswith("do_"):
                # V2 DYNAMIC GENERATION
                narrative_fragment = orchestrator.translate_plan_to_narrative([pddl_action], state["active_persona"])
                effective_action = f"visual {narrative_fragment}"
            else:
                effective_action = "start" if not prompt.strip() else "talk"
                if pddl_action and pddl_action != "None":
                    if any(x in pddl_action for x in ["deploy", "activate", "learn", "apply"]):
                        effective_action = pddl_action
                    elif "shift-context" in pddl_action:
                        effective_action = pddl_action

            payload = social_llm.generate_social_narrative(effective_action, adapter, prompt)
            
            # VISUAL GENERATION FOR RESPONSE
            img_path = None
            if st.session_state.get("visual_enabled", False) and "scene_description" in payload:
                try:
                    vis_gen = VisualGenerator()
                    # Resolve names
                    persona_id = state["active_persona"]
                    p_data = orchestrator.personas_data.get(persona_id, {})
                    p_name = p_data.get("name", persona_id)
                    p_desc = p_data.get("description", "A mysterious figure.") # Get Description
                    
                    # Resolve Image Reference Path
                    image_ref = p_data.get("properties", {}).get("image_reference")
                    image_ref_path = None
                    if image_ref:
                        image_ref_path = str(Path("npc_engine/config/social_world/nodes/personas") / image_ref)

                    loc_id = state.get("current_location", "unknown")
                    loc_data = orchestrator.locations_data.get(loc_id, {})
                    loc_name = loc_data.get("name", loc_id)
                    
                    with st.spinner("Visualizing scene..."):
                        img_path = vis_gen.generate_scene_visual(
                            payload["scene_description"], 
                            p_name, 
                            p_desc, 
                            loc_name,
                            image_ref_path=image_ref_path
                        )
                except Exception as e:
                    st.error(f"Visual gen failed. Ref: {image_ref_path}. Error: {e}")

            messages.append({"role": "assistant", "content": payload, "image": img_path})
            st.rerun()
