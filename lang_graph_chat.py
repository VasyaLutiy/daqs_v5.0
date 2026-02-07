import os
import yaml
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv

try:
    from langgraph.graph import StateGraph, END
except ImportError:
    raise SystemExit("langgraph not installed.")

load_dotenv()

from gamemaster.social_llm import (
    setup_gemini_client, setup_grok_client, 
    LLM_PROVIDER, GEMINI_MODEL, GROK_MODEL,
    format_dialogue
)

CONFIG_PATH = Path("npc_engine/config/social_world/nodes/personas/elves.yaml")
PLAYER_STATE_PATH = Path("player_state.json")

class ShadowGateNPCEngine:
    def __init__(self, persona_id: str, atlas: Dict[str, Any]):
        self.persona = next((p for p in atlas.get("personas", []) if p["id"] == persona_id), None)
        self.contexts = {c["id"]: c for c in self.persona["contexts"]}
        self.triggers = {t["id"]: t for t in self.persona["triggers"]}
        self.target_goal = "ctx_joined"
        self.graph = self._build_graph()
        
    def _get_real_inventory(self) -> List[str]:
        try:
            data = json.loads(PLAYER_STATE_PATH.read_text())
            return [k for k, v in data.get("inventory", {}).get("items", {}).items() if v > 0]
        except: return []

    def _get_llm_response(self, state: Dict[str, Any], player_input: str) -> str:
        ctx = self.contexts[state["current_context"]]
        concepts = state.get('concepts', [])
        res = state.get("last_action_result", "SUCCESS")
        
        # --- STRATEGIC DIRECTIVE (The Shadow Gate) ---
        directive = ""
        if "cpt_agreement" in concepts:
            directive = "The partnership is sealed. You are ready for the job."
        elif "cpt_partnership_offer" in concepts and "cpt_shadow_token" not in concepts:
            directive = "IMPORTANT: You accepted the idea of a job, but now you MUST be skeptical. Tell them gold isn't enough. You need to see a 'dark iron sign' (Shadow Token) to trust them."
        elif "cpt_shadow_token" in concepts:
            directive = "You've seen the coin. You are impressed. Now you can move to 'The Deal' and the scroll."
        else:
            directive = "Be dismissive. Ask for a real contract/job offer."

        logic_info = f"SYSTEM: {res}. "
        if res == "REJECTED":
            logic_info += f"REASON: {state.get('rejection_reason')}. Call them a liar/fraud."

        prompt = f"""Roleplay as {self.persona['name']}. {self.persona['description']}
        Context: {ctx.get('name')} | Known: {concepts}
        MISSION: {directive} | {logic_info}
        
        Player input: "{player_input}"
        
        STRICT RULES:
        1. If MISSION says 'Gold isn't enough', DO NOT sign the contract yet. 
        2. Use metaphors for shadow items. 1-2 sentences.
        """
        try:
            client_func = setup_grok_client if LLM_PROVIDER == "grok" else setup_gemini_client
            client = client_func()
            if LLM_PROVIDER == "grok":
                text = client.chat.completions.create(model=GROK_MODEL, messages=[{"role": "user", "content": prompt}]).choices[0].message.content
            else:
                text = client.models.generate_content(model=GEMINI_MODEL, contents=prompt).text
            return format_dialogue(text.strip())
        except Exception as e: return f"*Glares.* ({e})"

    def _nlu_classify(self, player_input: str, state: Dict[str, Any]) -> str:
        options = list(self.triggers.keys()) + list(self.contexts.keys())
        prompt = f"Input: '{player_input}'. Context: {state['current_context']}. Match to ID: {options}. Return ONLY ID."
        try:
            client_func = setup_grok_client if LLM_PROVIDER == "grok" else setup_gemini_client
            res = client_func().chat.completions.create(model=GROK_MODEL, messages=[{"role": "user", "content": prompt}]).choices[0].message.content.strip().replace("`", "") if LLM_PROVIDER == "grok" else client_func().models.generate_content(model=GEMINI_MODEL, contents=prompt).text.strip().replace("`", "")
            match = re.search(r"(trig_|ctx_)[a-zA-Z0-9_]+", res)
            return match.group(0) if match else "None"
        except: return "None"

    def _build_graph(self) -> Any:
        sg = StateGraph(dict)
        def logic_gate(state: Dict[str, Any]):
            new_state = state.copy(); next_step = state.get("next_step", "None")
            concepts = state.get("concepts", []); inv = self._get_real_inventory()
            new_state["last_action_result"] = "SUCCESS"; new_state["rejection_reason"] = ""

            if next_step in self.triggers:
                trig = self.triggers[next_step]
                
                # --- THE SHADOW GATE LOGIC ---
                if next_step == "trig_accept_partnership" and "cpt_shadow_token" not in concepts:
                    new_state["last_action_result"] = "REJECTED"
                    new_state["rejection_reason"] = "I don't trust you without proof of shadow ties (coin)."
                    return new_state
                
                req = trig.get("requires_item")
                if req and req not in inv:
                    new_state["last_action_result"] = "REJECTED"; new_state["rejection_reason"] = f"No {req}"
                else:
                    new_state["current_context"] = trig["parent_context"]
                    if trig.get("yields"): new_state["concepts"] = list(set(concepts) | {trig["yields"]})
            elif next_step in self.contexts:
                new_state["current_context"] = next_step
            
            return new_state
        sg.add_node("gate", logic_gate); sg.set_entry_point("gate"); sg.add_edge("gate", END)
        return sg.compile()

    def run_chat(self):
        state = {"concepts": ["cpt_quest_none"], "current_context": "ctx_tavern_intro", "next_step": None, "last_input": "Hello"}
        print(f"=== THE SHADOW GATE ENGINE ===")
        while True:
            # Auto-progress
            for cid in ["ctx_partnership", "ctx_joined"]:
                req = self.contexts.get(cid, {}).get("properties", {}).get("required_concept")
                if req in state["concepts"]:
                    state["current_context"] = cid

            response = self._get_llm_response(state, state["last_input"])
            print(f"\n\033[92mDolores:\033[0m {response}")
            if state['current_context'] == self.target_goal:
                print(f"\n\033[96m[SUCCESS] MISSION ACCOMPLISHED!\033[0m"); break

            player_input = input("\n\033[94mYou:\033[0m ").strip()
            if player_input.lower() in ["exit", "quit"]:
                break
            state["last_input"] = player_input
            state["next_step"] = self._nlu_classify(player_input, state)
            state = self.graph.invoke(state)
            print(f"  \033[90m[Logic] Attempt: {state['next_step']} | Result: {state['last_action_result']} | Concepts: {state['concepts']}\033[0m")

if __name__ == "__main__":
    atlas = yaml.safe_load(Path(CONFIG_PATH).read_text())
    ShadowGateNPCEngine("persona_dolores", atlas).run_chat()