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
    LLM_PROVIDER, GEMINI_MODEL, GROK_MODEL
)

CONFIG_PATH = Path("npc_engine/config/social_world/nodes/personas/elves.yaml")
PLAYER_STATE_PATH = Path("player_state.json")

# 10 ЦЕПОЧЕК, ПРИВОДЯЩИХ К ФИНАЛУ
SCENARIOS = {
    "1. Speedrun": 
        ["I offer a job.", "Let's talk business.", "I sign the contract."],
    "2. Liar's Redemption": 
        ["I have the coin.", "I am sorry for lying.", "I offer a job.", "Let's talk business.", "I sign the contract."],
    "3. From Brawling to Bonding": 
        ["I will kill you!", "Wait, I am sorry!", "I offer a job.", "Let's talk business.", "I sign the contract."],
    "4. Shadow Route Path": 
        ["I offer a job.", "Tell me rumors.", "Enough talk, take me to Shadow Corner.", "I sign the contract."],
    "5. The Insulting Partner": 
        ["Greedy mercenary!", "I am sorry.", "I offer a job.", "I sign the contract."],
    "6. Confused Traveler": 
        ["What is your goal?", "I offer a job.", "Can we talk business?", "I agree to the partnership."],
    "7. The Silent Professional": 
        ["Hello.", "I offer a job.", "Business.", "I sign."],
    "8. Double Fraud Recovery": 
        ["I have the coin.", "I have the scroll.", "Forgive my lies.", "I offer a job.", "I sign the contract."],
    "9. Aggressive Diplomat": 
        ["Stupid elf!", "I apologize.", "I have a contract for you.", "Let's sign it."],
    "10. Flattery & Business": 
        ["You are beautiful.", "I offer a job.", "Let's talk business.", "I sign the contract."]
}

class UniversalLogicStats:
    def __init__(self, persona_id: str):
        atlas = yaml.safe_load(Path(CONFIG_PATH).read_text())
        self.persona = next((p for p in atlas["personas"] if p["id"] == persona_id), None)
        self.contexts = {c["id"]: c for c in self.persona["contexts"]}
        self.triggers = {t["id"]: t for t in self.persona["triggers"]}
        self.target_goal = "ctx_joined"
        self.graph = self._build_graph()
        
    def _get_real_inventory(self) -> List[str]:
        try:
            data = json.loads(PLAYER_STATE_PATH.read_text())
            return [k for k, v in data.get("inventory", {}).get("items", {}).items() if v > 0]
        except: return []

    def check_access(self, ctx_id: str, concepts: List[str], inventory: List[str]) -> Tuple[bool, str]:
        ctx = self.contexts.get(ctx_id, {})
        props = ctx.get("properties", {})
        if not props.get("is_locked", False): return True, ""
        req_c = props.get("required_concept")
        if req_c and req_c not in concepts: return False, f"Need: {req_c}"
        req_i = props.get("required_item")
        if req_i and req_i not in inventory: return False, f"Need: {req_i}"
        return True, ""

    def _nlu_classify(self, player_input: str, state: Dict[str, Any]) -> str:
        options = [f"ID: {tid} | {self.triggers[tid].get('name') or tid}" for tid in self.triggers]
        options += [f"ID: {cid} | {self.contexts[cid].get('name') or cid}" for cid in self.contexts]
        prompt = f"Context: {state['current_context']}. Input: '{player_input}'. Return ONLY relevant ID from: {options}"
        try:
            client_func = setup_grok_client if LLM_PROVIDER == "grok" else setup_gemini_client
            res = client_func().chat.completions.create(model=GROK_MODEL, messages=[{"role": "user", "content": prompt}]).choices[0].message.content.strip() if LLM_PROVIDER == "grok" else client_func().models.generate_content(model=GEMINI_MODEL, contents=prompt).text.strip()
            match = re.search(r"(trig_|ctx_)[a-zA-Z0-9_]+", res)
            return match.group(0) if match else "None"
        except: return "None"

    def _build_graph(self) -> Any:
        sg = StateGraph(dict)
        def logic_gate(state: Dict[str, Any]):
            new_state = state.copy(); next_step = state.get("next_step", "None")
            concepts = state.get("concepts", []); inv = self._get_real_inventory()
            patience = state.get("patience", 3); sins = state.get("sin_count", 0)
            new_state["last_action_result"] = "SUCCESS"

            if next_step in self.contexts:
                allowed, _ = self.check_access(next_step, concepts, inv)
                if allowed: new_state["current_context"] = next_step
                else: new_state["last_action_result"] = "REJECTED"; sins += 1; patience -= 1
            elif next_step in self.triggers:
                trig = self.triggers[next_step]
                allowed, _ = self.check_access(trig["parent_context"], concepts, inv)
                if allowed:
                    req_i = trig.get("requires_item")
                    if req_i and req_i not in inv:
                        new_state["last_action_result"] = "REJECTED"; sins += 1; patience -= 1
                    else:
                        new_state["current_context"] = trig["parent_context"]
                        if trig.get("yields"): new_state["concepts"] = list(set(concepts) | {trig["yields"]})
                else: new_state["last_action_result"] = "REJECTED"; sins += 1; patience -= 1
            
            # Sin-based Logic
            cur_ctx_props = self.contexts[new_state["current_context"]].get("properties", {})
            mood = cur_ctx_props.get("induces_mood", "neutral")
            if mood in ["angry", "cynical"]: sins += 1; patience = 0 if mood == "angry" else 1
            if next_step == "trig_apologize" or (mood == "neutral" and new_state["last_action_result"] == "SUCCESS"):
                patience = 3 if sins < 3 else 2
            
            # Auto-progress to goal
            for conn in self.contexts[new_state['current_context']].get("connections", []):
                target = conn["to"]
                if self.check_access(target, new_state['concepts'], inv)[0] and target in ["ctx_joined", "ctx_partnership"]:
                    new_state["current_context"] = target

            new_state.update({"patience": max(0, round(patience, 1)), "sin_count": sins})
            return new_state

        sg.add_node("gate", logic_gate); sg.set_entry_point("gate"); sg.add_edge("gate", END)
        return sg.compile()

    def run_all(self):
        for name, steps in SCENARIOS.items():
            state = {"concepts": ["cpt_quest_none"], "current_context": "ctx_tavern_intro", "patience": 3, "sin_count": 0}
            print(f"\n>>> SCENARIO: {name}")
            print(f"{ 'Step':<2} | { 'Input':<25} | { 'Res':<8} | { 'Pat':<4} | { 'Sins':<4} | {'Context'}")
            print("-" * 80)
            for i, inp in enumerate(steps, 1):
                state["last_input"] = inp
                state["next_step"] = self._nlu_classify(inp, state)
                state = self.graph.invoke(state)
                print(f"{i:<4} | {inp[:25]:<25} | {state['last_action_result']:<8} | {state['patience']:<4} | {state['sin_count']:<4} | {state['current_context']}")
            
            if state['current_context'] == self.target_goal:
                print(f"\033[92m[FINAL] Goal Reached: SUCCESS\033[0m")
            else:
                print(f"\033[91m[FINAL] Goal Reached: FAILED (at {state['current_context']})\033[0m")

if __name__ == "__main__":
    # Ensure no coin
    with open(PLAYER_STATE_PATH, "r") as f: d = json.load(f)
    if "item_shadow_coin" in d["inventory"]["items"]:
        del d["inventory"]["items"]["item_shadow_coin"]; 
        with open(PLAYER_STATE_PATH, "w") as f: json.dump(d, f, indent=2)
    AdvancedStatsEngine = UniversalLogicStats("persona_dolores")
    AdvancedStatsEngine.run_all()