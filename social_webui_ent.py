import os
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

from npc_engine.bootstrap import init_logging

init_logging()

# API endpoints (enterprise FastAPI)
API_BASE = os.getenv("NPC_API_BASE", "http://localhost:8001")
API_PLAN = f"{API_BASE}/plan/exploration"
API_STATE = f"{API_BASE}/world/state"
API_QUEST = f"{API_BASE}/quest/difficulty"
API_PROCESS = f"{API_BASE}/process"
API_QUEST_ACCEPT = f"{API_BASE}/quest/accept"
API_SOCIAL_INIT = f"{API_BASE}/social/init"
API_SOCIAL_MSG = f"{API_BASE}/social/message"
API_WORLD_GRAPH = f"{API_BASE}/world/graph"
API_SOCIAL_GRAPH = f"{API_BASE}/social/graph"

PLAYER_STATE_FILE = Path("player_state.json")


# --- API helpers ---
# Some backend calls (LLM/visual) can take longer; use a generous default.
def _post(url: str, payload: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _get(url: str, params: Dict[str, Any], timeout: int = 10) -> Dict[str, Any]:
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# --- Local state helpers ---
def load_player_state() -> Dict[str, Any]:
    default_data = {
        "id": "player_001",
        "location": "forest_entrance",
        "inventory": {"items": {}},
        "knowledge": {
            "discovered_locations": ["forest_entrance"],
            "visited_locations": ["forest_entrance"],
        },
    }
    if PLAYER_STATE_FILE.exists():
        try:
            return json.loads(PLAYER_STATE_FILE.read_text())
        except Exception:
            return default_data
    return default_data


def save_player_state(data: Dict[str, Any]) -> None:
    try:
        PLAYER_STATE_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        st.warning(f"Failed to save player state: {e}")


# --- API wrappers ---
def api_get_state(player: Dict[str, Any]) -> Dict[str, Any]:
    return _get(API_STATE, {"player_id": player.get("id"), "location": player.get("location"), "goal": player.get("goal")})


def api_plan(player: Dict[str, Any], oracle: bool = False) -> Dict[str, Any]:
    return _post(API_PLAN, {"input_json": player, "oracle_mode": oracle})


def api_process(player: Dict[str, Any], oracle: bool = False) -> Dict[str, Any]:
    return _post(API_PROCESS, {"input_json": player, "oracle_mode": oracle})


def api_quest_difficulty(goal: Optional[str]) -> Optional[str]:
    if not goal:
        return None
    res = _post(API_QUEST, {"goal": goal})
    return res.get("concept")


def api_social_init(persona_id: str, player_state: Dict[str, Any], can_quest: bool = True) -> Dict[str, Any]:
    return _post(API_SOCIAL_INIT, {"persona_id": persona_id, "player_state": player_state, "can_quest": can_quest})


def api_social_message(persona_id: str, social_state: Dict[str, Any], player_state: Dict[str, Any], message: str, action: Optional[str] = None) -> Dict[str, Any]:
    payload = {"persona_id": persona_id, "social_state": social_state, "player_state": player_state, "message": message}
    if action:
        payload["action"] = action
    return _post(API_SOCIAL_MSG, payload)


def api_world_graph(current_loc: str, discovered: List[str], target: Optional[str] = None) -> Optional[str]:
    try:
        res = _post(API_WORLD_GRAPH, {"current_location": current_loc, "discovered": discovered, "target_node": target})
        return res.get("graph")
    except Exception:
        return None


def api_social_graph(persona_id: str, social_state: Dict[str, Any], target_goal: Optional[str]) -> Optional[str]:
    try:
        res = _post(API_SOCIAL_GRAPH, {"persona_id": persona_id, "social_state": social_state, "target_goal": target_goal})
        return res.get("graph")
    except Exception:
        return None


def api_quest_accept(quest_goal: str, quest_name: str, player_state: Dict[str, Any], social_state: Dict[str, Any]) -> Dict[str, Any]:
    return _post(API_QUEST_ACCEPT, {"quest_goal": quest_goal, "quest_name": quest_name, "player_state": player_state, "social_state": social_state})


def _format_dialogue(text: str) -> str:
    """Clean up LLM dialogue and prepend markdown emoji icons with soft breaks."""
    if not text:
        return ""
    if text.startswith("\"") and text.endswith("\""):
        text = text[1:-1]
    cleaned = re.sub(r"<br[^>]*>", "\n", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace("\r", "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    paragraphs = []
    for block in cleaned.split("\n\n"):
        parts = [p.strip() for p in block.split("\n") if p.strip()]
        if parts:
            paragraphs.append(" ".join(parts))
    icons = ["✨", "🛡️", "🔥", "🌟", "🕯️", "🌞"]
    out_blocks = []
    for idx, para in enumerate(paragraphs):
        icon = icons[idx % len(icons)]
        sentences = re.split(r"(?<=[.!?])\\s+", para)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            continue
        # Soft breaks: two spaces + newline between sentences
        joined = ("  \n").join(sentences)
        out_blocks.append(f"{icon} {joined}")
    return "\n\n".join(out_blocks)


def _render_message(content: Any) -> str:
    """Return markdown string for chat message content."""
    if isinstance(content, dict):
        dialog = content.get("dialogue") or ""
        return _format_dialogue(dialog)
    rendered = _format_dialogue(str(content))
    # Ensure at least one leading icon
    if not rendered.startswith(("✨", "🛡️", "🔥", "🌟", "🕯️", "🌞")):
        rendered = f"✨ {rendered}"
    return rendered


# --- Session bootstrap ---
st.set_page_config(page_title="DAQS v5.1 Enterprise UI", page_icon="🌍", layout="wide")

if "player_data" not in st.session_state:
    st.session_state.player_data = load_player_state()
if "world_cache" not in st.session_state:
    st.session_state.world_cache = {}
if "world_graph" not in st.session_state:
    st.session_state.world_graph = None
if "social_state" not in st.session_state:
    st.session_state.social_state = {}
if "social_messages" not in st.session_state:
    st.session_state.social_messages = []
if "game_mode" not in st.session_state:
    st.session_state.game_mode = "WORLD"  # WORLD | SOCIAL
if "visual_enabled" not in st.session_state:
    st.session_state.visual_enabled = False


# --- UI rendering helpers ---
def render_sidebar():
    with st.sidebar:
        st.header("⚙️ System Core")
        mode_label = "🌍 WORLD MODE" if st.session_state.game_mode == "WORLD" else "💬 SOCIAL MODE"
        st.info(f"Current State: **{mode_label}**")
        vis_status = "🟢 Enabled" if st.session_state.get("visual_enabled") else "⚪ Disabled"
        st.caption(f"Visual Engine: {vis_status}")

        if st.button("Hard Reset"):
            st.session_state.clear()
            st.session_state.player_data = load_player_state()
            st.session_state.game_mode = "WORLD"
            st.rerun()

        st.divider()

        st.subheader("🎒 Inventory")
        inv = st.session_state.player_data.get("inventory", {}).get("items", {})
        if inv:
            for item_id, count in inv.items():
                st.write(f"- {item_id.replace('_', ' ').title()}: {count}")
        else:
            st.caption("Empty")

        # Context-aware quick actions (e.g., Dolores shadow coin) — kept in sidebar for visibility
        if st.session_state.game_mode == "SOCIAL":
            social_state = st.session_state.get("social_state", {})
            moves = set(social_state.get("available_moves", []))
            concepts = set(social_state.get("concepts", []))
            current_ctx = social_state.get("current_context")
            has_coin = inv.get("item_shadow_coin", 0) > 0

            coin_trigger = "activate-trigger player ctx_neutral_talk trig_find_coin cpt_shadow_token"
            combo_apply = "apply-combo-concept player ctx_neutral_talk ctx_shadow_entry cpt_shadow_rumor cpt_shadow_token"
            allowed_contexts = {"ctx_neutral_talk", "ctx_shadow_entry", "ctx_shadow_deal"}

            show_coin_btn = (
                current_ctx in allowed_contexts
                and has_coin
                and "cpt_shadow_rumor" in concepts
            )

            if show_coin_btn:
                st.markdown("**Shadow Deal Shortcut**")
                if st.button("🤝 Share Black Iron Coin", key="share_shadow_coin_sidebar"):
                    _social_chat_input("share coin", action=coin_trigger)
                    # If combo already possible, attempt it immediately
                    if combo_apply in moves or ("cpt_shadow_token" in concepts and "cpt_shadow_rumor" in concepts):
                        _social_chat_input("unlock shadow", action=combo_apply)
                    st.rerun()

        st.divider()

        if "goal" in st.session_state.player_data and st.session_state.player_data.get("goal"):
            st.subheader("🎯 Current Quest")
            goal = st.session_state.player_data["goal"]
            # Try to resolve goal to quest name from world cache
            quest_name = None
            meta = st.session_state.world_cache.get("metadata", {})
            quests = meta.get("available_quests", [])
            for q in quests:
                if q.get("goal") == goal:
                    quest_name = q.get("name")
                    break
            st.write(quest_name or goal)


def _sync_world():
    player = st.session_state.player_data
    try:
        res = api_get_state(player)
        st.session_state.world_cache = res
    except Exception as e:
        st.error(f"World sync failed: {e}")
        return
    discovered = player.get("knowledge", {}).get("discovered_locations", [])
    graph = api_world_graph(player.get("location", "unknown"), discovered)
    st.session_state.world_graph = graph


def _handle_navigation(target_id: str):
    player = st.session_state.player_data
    player["location"] = target_id
    know = player.setdefault("knowledge", {})
    disc = know.setdefault("discovered_locations", [])
    visi = know.setdefault("visited_locations", [])
    if target_id not in disc:
        disc.append(target_id)
    if target_id not in visi:
        visi.append(target_id)
    save_player_state(player)
    _sync_world()
    st.rerun()


def _handle_pickup(item: Dict[str, Any]):
    inv = st.session_state.player_data.setdefault("inventory", {}).setdefault("items", {})
    inv[item["id"]] = inv.get(item["id"], 0) + 1
    save_player_state(st.session_state.player_data)
    _sync_world()
    st.rerun()


def _start_social(npc: Dict[str, Any]):
    persona_id = npc.get("social_persona", "persona_cyber")
    can_quest = npc.get("dialogue_quest", False)
    try:
        res = api_social_init(persona_id, st.session_state.player_data, can_quest=can_quest)
        st.session_state.social_state = res.get("social_state", {})
        st.session_state.social_messages = res.get("history", [])
        st.session_state.social_state["active_persona"] = persona_id
        st.session_state.social_state["available_moves"] = []
        graph = api_social_graph(persona_id, st.session_state.social_state, st.session_state.social_state.get("target_goal"))
        st.session_state.social_state["graph"] = graph
        st.session_state.social_state["can_quest"] = can_quest
        st.session_state.game_mode = "SOCIAL"
        st.success(f"Talking to {persona_id}")
        st.rerun()
    except Exception as e:
        st.error(f"Social init failed: {e}")


def render_right_column():
    with st.container(height=800, border=True):
        st.write("### 🎮 Command Deck")
        if st.session_state.game_mode == "WORLD":
            if not st.session_state.world_cache:
                _sync_world()
            cache = st.session_state.world_cache
            meta = cache.get("metadata", {})
            loc = meta.get("location", st.session_state.player_data.get("location", "unknown"))
            st.subheader(f"📍 {loc.replace('_', ' ').title()}")

            img_path = Path(f"static/images/locations/{loc}.png")
            if img_path.exists():
                st.image(str(img_path), caption=f"View of {loc}", width="stretch")

            if st.session_state.world_graph:
                st.graphviz_chart(st.session_state.world_graph)
            with st.expander("🔍 Raw World Cache"):
                st.json(cache)

            st.divider()

            st.write("#### 👤 Entities Detected")
            npcs = cache.get("npcs_nearby") or meta.get("npcs_nearby", [])
            if npcs:
                for npc in npcs:
                    with st.expander(f"{npc.get('name', npc.get('id'))}", expanded=True):
                        st.caption(f"_{npc.get('personality','')}_" if npc.get("personality") else "")
                        can_quest = npc.get("dialogue_quest", False)
                        show_quest_label = can_quest and npc.get("social_persona") != "persona_dolores"
                        label = f"Talk to {npc.get('name')} (Quest)" if show_quest_label else f"Talk to {npc.get('name')}"
                        if st.button(label, key=f"talk_{npc.get('id')}"):
                            _start_social(npc)
            else:
                st.caption("No biological or digital signatures detected.")

            st.divider()

            st.write("#### 🧭 Navigation")
            exits = cache.get("exits") or meta.get("exits", [])
            cols = st.columns(2)
            for i, exit_node in enumerate(exits):
                eid = exit_node["id"]
                ename = exit_node["name"]
                label = ename.replace('_', ' ').title()
                if cols[i % 2].button(f"Go to {label}", key=f"nav_{eid}"):
                    _handle_navigation(eid)

            if not exits:
                st.caption("No visible exits.")

            st.divider()

            st.write("#### 📦 Items Detected")
            items = cache.get("items_nearby") or meta.get("items_nearby", [])
            if items:
                for item in items:
                    if st.button(f"Pickup {item['name']}", key=f"pickup_{item['id']}"):
                        _handle_pickup(item)
            else:
                st.caption("No items here.")
        else:
            st.subheader("💬 Interaction Active")
            if st.button("🚪 Leave Conversation"):
                st.session_state.game_mode = "WORLD"
                if "goal" in st.session_state.player_data:
                    del st.session_state.player_data["goal"]
                save_player_state(st.session_state.player_data)
                st.rerun()

            st.divider()

            # Mission board equivalent (only for quest-capable personas)
            persona_id = st.session_state.social_state.get("active_persona", st.session_state.social_state.get("persona_id", ""))
            can_quest = st.session_state.social_state.get("can_quest", False)
            if persona_id != "persona_dolores" and can_quest:
                meta = st.session_state.world_cache.get("metadata", {})
                quests = meta.get("available_quests", [])
                if quests:
                    st.write("#### 📜 Missions")
                    for quest in quests:
                        quest_id = quest["id"]
                        quest_name = quest["name"]
                        quest_goal = quest["goal"]
                        if st.button(f"Ask about {quest_name}", key=f"quest_{quest_id}"):
                            try:
                                res = api_quest_accept(quest_goal, quest_name, st.session_state.player_data, st.session_state.social_state)
                                plan = res.get("plan", [])
                                payload = res.get("payload")
                                st.session_state.social_messages.append({"role": "assistant", "content": payload or {"dialogue": f"Plan: {plan}"}})
                                # Store pending quest offer to confirm later
                                st.session_state.pending_quest = {"id": quest_id, "name": quest_name, "goal": quest_goal, "plan": plan}
                                st.success(f"Quest briefed: {quest_name}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Quest briefing failed: {e}")

                # Confirmation after briefing
                pending = st.session_state.get("pending_quest")
                if pending:
                    st.divider()
                    st.info(f"Ready to accept quest: {pending.get('name')}")
                    if st.button("✅ Accept & Start Journey", type="primary"):
                        st.session_state.player_data["goal"] = pending.get("goal")
                        save_player_state(st.session_state.player_data)
                        st.session_state.game_mode = "WORLD"
                        _sync_world()
                        st.session_state.pending_quest = None
                        st.rerun()

            st.write("#### Mind Map")
            graph = st.session_state.social_state.get("graph")
            if graph:
                st.graphviz_chart(graph)

            st.write("#### Available Moves (backend)")
            st.json(st.session_state.social_state.get("available_moves", []))


def render_chat():
    container = st.container(height=700)
    messages = st.session_state.world_cache.get("history", []) if st.session_state.game_mode == "WORLD" else st.session_state.social_messages

    for msg in messages:
        with container.chat_message(msg.get("role", "assistant")):
            if msg.get("image"):
                try:
                    img_path = Path(msg["image"])
                    if img_path.exists():
                        st.image(str(img_path), width="stretch")
                except Exception:
                    pass

            content = msg.get("content", msg)
            if isinstance(content, dict):
                if "scene_description" in content:
                    with st.expander("👁️ Atmosphere"):
                        st.write(content.get("scene_description", ""))
                if "internal_monologue" in content:
                    with st.expander("🧠 NPC Thoughts"):
                        st.write(content.get("internal_monologue", ""))
                st.markdown(_render_message(content))
            else:
                st.markdown(_render_message(content))


def _world_chat_input(prompt: str):
    st.session_state.player_data["goal"] = prompt if " " not in prompt else st.session_state.player_data.get("goal")
    try:
        res = api_plan(st.session_state.player_data, oracle=True)
        st.session_state.world_cache = res
        plan_text = "\n".join(res.get("plan", []))
        narrative = f"**System:** Processing action...\n\nPlan:\n```\n{plan_text}\n```"
        if res.get("error"):
            narrative = f"❌ **Error:** {res['error']}"
        history = st.session_state.world_cache.setdefault("history", [])
        history.append({"role": "assistant", "content": narrative})
    except Exception as e:
        st.error(f"World action failed: {e}")


def _social_chat_input(prompt: str, action: Optional[str] = None):
    persona_id = st.session_state.social_state.get("active_persona", st.session_state.social_state.get("persona_id", "persona_cyber"))
    try:
        res = api_social_message(persona_id, st.session_state.social_state, st.session_state.player_data, prompt, action)
        st.session_state.social_state = res.get("social_state", st.session_state.social_state)
        meta = res.get("metadata", {})
        if meta:
            st.session_state.social_state["available_moves"] = meta.get("valid_moves", [])
        graph = api_social_graph(persona_id, st.session_state.social_state, st.session_state.social_state.get("target_goal"))
        st.session_state.social_state["graph"] = graph
        st.session_state.social_messages.append({"role": "user", "content": prompt})
        reply = res.get("reply")
        img = res.get("image_path")
        st.session_state.social_messages.append({"role": "assistant", "content": reply, "image": img})
    except Exception as e:
        st.error(f"Social message failed: {e}")


def main_layout():
    st.title("DAQS v5.1: Unified World (Enterprise Thin Client)")
    render_sidebar()

    col_chat, col_right = st.columns([0.65, 0.35])
    with col_right:
        render_right_column()

    with col_chat:
        render_chat()
        prompt = st.chat_input("Your Action..." if st.session_state.game_mode == "WORLD" else "Say something...")
        if prompt:
            if st.session_state.game_mode == "WORLD":
                _world_chat_input(prompt)
            else:
                _social_chat_input(prompt)
            st.rerun()

    st.subheader("Quest Difficulty (backend)")
    player_goal = st.session_state.player_data.get("goal")
    if player_goal:
        if st.button("Check difficulty"):
            try:
                concept = api_quest_difficulty(player_goal)
                st.write(f"Difficulty concept: {concept}")
            except Exception as e:
                st.error(f"Difficulty check failed: {e}")


if not st.session_state.world_cache:
    _sync_world()

main_layout()
