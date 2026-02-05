import streamlit as st
import json
from pathlib import Path
from PIL import Image
from npc_engine.engine.master.pddl_orchestrator import PDDLOrchestrator
from gamemaster import social_llm
from .social_web_handle import handle_npc_interaction, handle_navigation, handle_item_pickup, handle_leave_conversation, handle_quest_acceptance
from .social_web_libs import sync_world, save_player_state, PLAYER_STATE_FILE

def render_sidebar():
    """
    Render the application sidebar with system controls and player status.
    
    Displays the current game mode, provides system reset functionality,
    and shows player inventory and quest status. The sidebar serves as
    the primary control panel for game state management and player information.
    
    Components:
        - Game Mode Indicator: Shows current WORLD/SOCIAL mode
        - Hard Reset Button: Complete system reset to initial state
        - Inventory Display: Current items and quantities
        - Quest Status: Active goal and progress information
        - Mind Map: Dialogue state visualization (context-dependent)
    
    Reset Functionality:
        - Switches to WORLD mode
        - Clears all message histories
        - Reloads player state from disk
        - Persists the reset state
    
    Inventory Display:
        - Shows all items in player_data["inventory"]["items"]
        - Displays quantities for stackable items
        - Updates dynamically with player state changes
    
    Quest Status:
        - Shows active quest goal (if any)
        - Displays quest difficulty analysis
        - Provides quest completion feedback
    
    Mind Map:
        - In SOCIAL mode: Shows dialogue context graph
        - In WORLD mode: Shows world navigation graph
        - Highlights current position and target goals
        - Uses GraphViz for visualization
    
    Note:
        The sidebar is always visible and provides essential game state
        information and controls regardless of current mode.
    """
    with st.sidebar:
        st.header("⚙️ System Core")

        mode_label = "🌍 WORLD MODE" if st.session_state.game_mode == "WORLD" else "💬 SOCIAL MODE"
        st.info(f"Current State: **{mode_label}**")
        
        # VISUAL STATUS
        vis_status = "🟢 Enabled" if st.session_state.get("visual_enabled") else "⚪ Disabled"
        st.caption(f"Visual Engine: {vis_status}")

        if st.button("Hard Reset"):
            # Reset everything including the engine cache
            if "engine" in st.session_state:
                del st.session_state.engine
            st.session_state.game_mode = "WORLD"
            st.session_state.world_messages = []
            st.session_state.social_messages = []
            if PLAYER_STATE_FILE.exists():
                with open(PLAYER_STATE_FILE, 'r') as f:
                    st.session_state.player_data = json.load(f)
            save_player_state(st.session_state.player_data)
            st.rerun()

        st.divider()

        # Inventory Display
        st.subheader("🎒 Inventory")
        inventory = st.session_state.player_data.get("inventory", {}).get("items", {})
        if inventory:
            for item_id, count in inventory.items():
                st.write(f"- {item_id.replace('_', ' ').title()}: {count}")
        else:
            st.caption("Empty")

        st.divider()

        # Current Quest Display
        if "goal" in st.session_state.player_data:
            goal = st.session_state.player_data["goal"]
            if goal.startswith("(has-item"):
                import re
                match = re.search(r'\(has-item\s+\w+\s+(\w+)\)', goal)
                if match:
                    item_id = match.group(1)
                    meta = st.session_state.world_cache.get("metadata", {})
                    quests = meta.get("available_quests", [])
                    for q in quests:
                        if q["id"] == item_id:
                            st.subheader("🎯 Current Quest")
                            st.write(f"**{q['name']}**")
                            break

        if st.session_state.game_mode == "SOCIAL":
            st.subheader("🧠 Mind Map")
            engine = st.session_state.engine
            s = st.session_state.social_state
            try:
                # Get target goal from active persona
                persona_id = s.get("active_persona", "persona_cyber")
                pddl_orch = PDDLOrchestrator()
                meta = pddl_orch.get_persona_metadata(persona_id)
                target_goal = meta.get("target_goal", "ctx_core")

                graph = engine.render_graph(s, target_goal)
                st.graphviz_chart(graph)
            except Exception as e:
                st.caption(f"Mind map unavailable: {str(e)}")

            st.caption(f"Context: {s['current_context']}")
            st.caption(f"Concepts: {len(s['concepts'])}")

def render_right_column():
    """
    Render the right column with mode-specific game controls and actions.
    
    Provides the primary interface for player actions based on current game mode.
    In WORLD mode, shows exploration and interaction options. In SOCIAL mode,
    displays dialogue controls and NPC interaction management.
    
    WORLD Mode Features:
        - World synchronization controls
        - Location navigation options
        - NPC interaction buttons
        - Item pickup actions
        - Quest acceptance interface
        - Available moves debugging
    
    SOCIAL Mode Features:
        - Dialogue input interface
        - NPC-initiated offer/flirt handling
        - Conversation flow controls
        - Social state debugging
        - Mind map visualization
        - Context transition management
    
    NPC Offer System:
        - Automatically detects available NPC offers
        - Prioritizes flirting over partnership offers
        - Applies offers immediately when conditions met
        - Generates appropriate dialogue responses
    
    Debug Information:
        - Shows current context and active persona
        - Lists all available moves
        - Displays NPC offer/flirt status
        - Provides selected action feedback
    
    Layout:
        - Fixed height container (800px) with border
        - Command Deck header
        - Mode-specific control sections
        - Debug expandable sections
    
    Note:
        This column contains the most interactive elements and changes
        significantly based on game mode and current state.
    """
    with st.container(height=800, border=True):
        st.write("### 🎮 Command Deck")

        # === WORLD CONTROLS ===
        if st.session_state.game_mode == "WORLD":
            # Sync world state on render if empty
            if not st.session_state.world_cache:
                sync_world(oracle=True)

            meta = st.session_state.world_cache.get("metadata", {})

            # DEBUG
            with st.expander("🔍 Raw World Cache"):
                st.write(st.session_state.world_cache)

            loc = meta.get("location", "Unknown")
            st.subheader(f"📍 {loc.replace('_', ' ').title()}")

            # VISUAL DISPLAY (Generated by Gemini)
            img_path = Path(f"static/images/locations/{loc}.png")
            if img_path.exists():
                st.image(str(img_path), caption=f"View of {loc}", width="stretch")

            # WORLD MAP (First Class Citizen now)
            engine = st.session_state.engine
            discovered = st.session_state.player_data.get("knowledge", {}).get("discovered_locations", [])
            w_graph = engine.render_world_graph(loc, discovered)
            st.graphviz_chart(w_graph)

            st.divider()

            # NPC Interaction
            st.write("#### 👤 Entities Detected")
            npcs = meta.get("npcs_nearby", [])
            if npcs:
                for npc in npcs:
                    with st.expander(f"{npc['name']}", expanded=True):
                        st.caption(f"_{npc['personality']}_")

                        can_quest = npc.get("dialogue_quest", False)
                        btn_label = f"Talk to {npc['name']} (Quest)" if can_quest else f"Talk to {npc['name']}"

                        if st.button(btn_label, key=f"talk_{npc['id']}"):
                            handle_npc_interaction(npc, can_quest, loc)
            else:
                st.caption("No biological or digital signatures detected.")

            st.divider()

            # Navigation
            st.write("#### 🧭 Navigation")
            exits = meta.get("exits", [])
            cols = st.columns(2)
            discovered = st.session_state.player_data.get("knowledge", {}).get("discovered_locations", [])

            for i, exit_node in enumerate(exits):
                eid = exit_node["id"]
                ename = exit_node["name"]
                label = ename.replace('_', ' ').title()
                if eid not in discovered:
                    label = f"Unknown Path ({eid})"

                if cols[i % 2].button(f"Go to {label}", key=f"nav_{eid}"):
                    handle_navigation(eid)

            if not exits:
                st.caption("No visible exits.")

            st.divider()

            # Item Collection
            st.write("#### 📦 Items Detected")
            items = meta.get("items_nearby", [])
            if items:
                for item in items:
                    if st.button(f"Pickup {item['name']}", key=f"pickup_{item['id']}"):
                        handle_item_pickup(item)
            else:
                st.caption("No items here.")

        # === SOCIAL CONTROLS ===
        else:  # SOCIAL MODE
            st.subheader("💬 Interaction Active")
            st.warning("Encryption: Secure")

            # MIND MAP in Social Mode
            engine = st.session_state.engine
            s = st.session_state.social_state
            try:
                # Get target goal from active persona
                persona_id = s.get("active_persona", "persona_cyber")
                pddl_orch = PDDLOrchestrator()
                meta = pddl_orch.get_persona_metadata(persona_id)
                target_goal = meta.get("target_goal", "ctx_core")

                graph = engine.render_graph(s, target_goal)
                st.graphviz_chart(graph)
            except Exception as e:
                st.caption(f"Mind map unavailable: {str(e)}")

            if st.button("🚪 Leave Conversation"):
                handle_leave_conversation()

            st.divider()

            # --- MISSION BRIEFING LOGIC ---
            current_ctx = s.get("current_context")
            if current_ctx == "ctx_quest_offer" or current_ctx.endswith("_quest_offer"):
                st.info("⚡ Mission Board")

                # Fetch available quests from the WORLD state
                quests = st.session_state.world_cache.get("metadata", {}).get("available_quests", [])

                if not quests:
                    st.caption("No missions available at this time.")
                else:
                    for quest in quests:
                        quest_id = quest["id"]
                        quest_name = quest["name"]
                        quest_goal = quest["goal"]

                        if st.button(f"📜 Ask about: {quest_name}", key=f"quest_{quest_id}"):
                            handle_quest_acceptance(quest_goal, quest_name)

                # Option to confirm and leave
                if st.session_state.player_data.get("goal"):
                    st.divider()
                    if st.button("✅ Accept & Start Journey", type="primary"):
                        st.session_state.game_mode = "WORLD"
                        st.rerun()

            st.write("#### Available Moves")
            state = st.session_state.social_state.copy()
            state["player_data"] = st.session_state.player_data
            moves = engine.get_valid_moves(state)
            for m in moves:
                st.code(m, language="bash")

def render_chat():
    """
    Render the main chat/narrative display column with message history.
    
    Displays the conversation flow and narrative content for both WORLD and
    SOCIAL game modes. Uses Streamlit's chat message components for clean
    presentation of dialogue, system messages, and narrative descriptions.
    
    Message Types:
        - User messages: Player input and commands
        - Assistant messages: NPC dialogue, system responses, and narratives
        - Special content: Scene descriptions, atmosphere, and formatted text
    
    Content Structure:
        Each message dict contains:
        - "role": "user" or "assistant"
        - "content": String or dict with dialogue/scene_description keys
    
    Rendering Logic:
        - Extracts appropriate message history based on game mode
        - Uses chat_message containers for proper chat UI
        - Handles both simple string content and structured content
        - Supports HTML rendering for formatted dialogue
        - Displays atmosphere descriptions in expandable sections
    
    Layout:
        - Fixed height container (700px) for consistent chat area
        - Scrollable message history
        - Proper chat bubble styling with role-based colors
        - Expandable sections for additional content
    
    Integration:
        - Reads from st.session_state.world_messages (WORLD mode)
        - Reads from st.session_state.social_messages (SOCIAL mode)
        - Updates automatically when message lists change
    
    Special Features:
        - Atmosphere rendering with 👁️ icon
        - Dialogue with 💬 formatting
        - HTML-safe content rendering
        - Responsive chat interface
    
    Note:
        This is the primary narrative display area where all story content,
        dialogue, and system feedback is presented to the player.
    """
    container = st.container(height=700)

    # RENDER MESSAGES
    messages = st.session_state.world_messages if st.session_state.game_mode == "WORLD" else st.session_state.social_messages

    for msg in messages:
        with container.chat_message(msg["role"]):
            # Render Dynamic Visual
            if msg.get("image"):
                try:
                    img_val = msg["image"]
                    img_path = Path(img_val) if isinstance(img_val, str) else img_val
                    if isinstance(img_path, Path) and not img_path.exists():
                        st.warning(f"Missing image: {img_path}")
                    elif img_path:
                        try:
                            # Validate image can be opened to avoid PIL UnidentifiedImageError
                            with open(img_path, "rb") as f:
                                Image.open(f).verify()  # type: ignore[attr-defined]
                            st.image(img_path, width="stretch")
                        except Exception as e:
                            st.warning(f"Image failed to render (corrupt?): {e}")
                except Exception as e:
                    st.warning(f"Image failed to render: {e}")

            if isinstance(msg["content"], dict):
                # JSON Payload
                with st.expander("👁️ Atmosphere"):
                    st.write(msg["content"].get("scene_description", ""))
                
                # NEW: Meta-Awareness / Internal Monologue
                if "internal_monologue" in msg["content"]:
                    with st.expander("🧠 NPC Thoughts (Dev Mode)"):
                        st.write(msg["content"].get("internal_monologue", ""))

                st.markdown(msg["content"].get("dialogue", ""), unsafe_allow_html=True)
            else:
                st.markdown(msg["content"])

    # --- NPC INITIATED OFFERS (Check for available NPC offers) ---
    if st.session_state.game_mode == "SOCIAL":
        # CHECK LAST MESSAGE ROLE
        # NPC only initiates spontaneous actions if the player has already spoken.
        # This prevents "message bursts" during dialogue start.
        last_msg_role = st.session_state.social_messages[-1]["role"] if st.session_state.social_messages else "assistant"

        if last_msg_role == "user":
            state = st.session_state.social_state.copy()
            state["player_data"] = st.session_state.player_data
            available_moves = st.session_state.engine.get_valid_moves(state)
            npc_offer_moves = [move for move in available_moves if move.startswith("npc-offer")]
            npc_flirt_moves = [move for move in available_moves if move.startswith("npc-flirt")]

            # Prioritize flirting over offers
            if npc_flirt_moves:
                npc_action = npc_flirt_moves[0]
                action_type = "flirt"
            elif npc_offer_moves:
                npc_action = npc_offer_moves[0]
                action_type = "offer"
            else:
                npc_action = None

            if npc_action:
                with st.spinner(f"NPC is initiating {action_type}..."):
                    # Apply the NPC action
                    st.session_state.engine.apply_action(npc_action, st.session_state.social_state)

                    # Generate dialogue for the NPC action
                    payload = social_llm.generate_social_narrative(npc_action, st.session_state.social_state)
                    st.session_state.social_messages.append({"role": "assistant", "content": payload})
                    st.rerun()

        # DEBUG: Show available moves (Always visible in debug expander)
        with st.expander("🐛 Debug: Available Moves"):
            st.write(f"Current context: {st.session_state.social_state.get('current_context')}")
            st.write(f"Active persona: {st.session_state.social_state.get('active_persona')}")
            # Re-calculate moves for debug display if not in user turn
            state_dbg = st.session_state.social_state.copy()
            state_dbg["player_data"] = st.session_state.player_data
            moves_dbg = st.session_state.engine.get_valid_moves(state_dbg)
            st.write(f"All moves: {moves_dbg}")
            st.write(f"Last message role: {last_msg_role}")
