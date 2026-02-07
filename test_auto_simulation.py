import os
import yaml
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv
from google import genai
from openai import OpenAI

try:
    from langgraph.graph import StateGraph, END
except ImportError:
    raise SystemExit("langgraph not installed.")

load_dotenv()

# CLIENTS
grok_client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1")
gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

GROK_MODEL = os.environ.get("GROK_MODEL", "grok-2-latest")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")

CONFIG_PATH = Path("npc_engine/config/social_world/nodes/personas/elves.yaml")
PLAYER_STATE_PATH = Path("player_state.json")

class StrategicNPCEngine:
    def __init__(self):
        atlas = yaml.safe_load(Path(CONFIG_PATH).read_text())
        self.persona = atlas["personas"][0]
        self.contexts = {c["id"]: c for c in self.persona["contexts"]}
        self.triggers = {t["id"]: t for t in self.persona["triggers"]}
        self.graph = self._build_graph()

    def _get_real_inventory(self) -> List[str]:
        try:
            data = json.loads(PLAYER_STATE_PATH.read_text())
            return [k for k, v in data.get("inventory", {}).get("items", {}).items() if v > 0]
        except: return []

    def nlu(self, player_input: str, state: Dict[str, Any]) -> str:
        options = [f"ID: {tid} | {self.triggers[tid].get('name') or tid}" for tid in self.triggers]
        options += [f"ID: {cid} | {self.contexts[cid].get('name') or cid}" for cid in self.contexts]
        
        prompt = f"""
        PLAYER INPUT: "{player_input}"
        CONTEXT: {state['current_context']}
        AVAILABLE IDs: {options}
        
        TASK: Return ONLY the ID string.
        - If they mention 'shadow coin' or 'black iron', pick 'trig_find_coin'.
        - If they offer gold/runes/hire, pick 'trig_hire_companion'.
        """
        try:
            res = gemini_client.models.generate_content(model=GEMINI_MODEL, contents=prompt).text.strip()
            match = re.search(r"(trig_|ctx_)[a-zA-Z0-9_]+", res)
            return match.group(0) if match else "None"
        except: return "None"

    def respond(self, state: Dict[str, Any], player_input: str) -> str:
        res = state.get("last_action_result", "SUCCESS")
        concepts = state.get("concepts", [])
        
        # --- THE STUBBORN DIRECTIVE ---
        if "cpt_shadow_token" not in concepts:
            directive = "You are UNIMPRESSED by runes, gold, or promises. You demand a 'sign of shadows' or 'dark iron proof'. Do NOT accept them into the party yet."
        else:
            directive = "You saw the shadow coin. You are satisfied. Now ask them to formally sign the agreement."

        prompt = f"Roleplay as Dolores. DIRECTIVE: {directive}. Logic Result: {res}. Concepts: {concepts}. Player said: '{player_input}'. 1-2 sentences."
        try:
            return gemini_client.models.generate_content(model=GEMINI_MODEL, contents=prompt).text.strip()
        except: return "*Stares coldly. *"

    def _build_graph(self) -> Any:
        sg = StateGraph(dict)
        def logic_gate(state: Dict[str, Any]):
            new_state = state.copy(); next_step = state.get("next_step", "None")
            concepts = state.get("concepts", []); inv = self._get_real_inventory()
            new_state["last_action_result"] = "SUCCESS"; new_state["rejection_reason"] = ""
            
            # --- THE STRATEGIC OVERRIDE (LangGraph Power) ---
            # Block ANY hire attempts if the shadow coin is not present
            if next_step == "trig_hire_companion" or next_step == "trig_accept_partnership":
                if "item_shadow_coin" not in inv and "cpt_shadow_token" not in concepts:
                    new_state["last_action_result"] = "REJECTED"
                    new_state["rejection_reason"] = "Generic offerings are not enough. Need shadow proof."
                    return new_state

            if next_step in self.triggers:
                trig = self.triggers[next_step]
                req = trig.get("requires_item")
                if req and req not in inv:
                    new_state["last_action_result"] = "REJECTED"
                    new_state["rejection_reason"] = f"Missing {req}"
                else:
                    new_state["current_context"] = trig["parent_context"]
                    if trig.get("yields"): new_state["concepts"] = list(set(concepts) | {trig["yields"]})
            elif next_step in self.contexts:
                new_state["current_context"] = next_step
            
            if "cpt_agreement" in new_state["concepts"]: new_state["current_context"] = "ctx_joined"
            return new_state
        sg.add_node("gate", logic_gate); sg.set_entry_point("gate"); sg.add_edge("gate", END)
        return sg.compile()

def grok_reactive_act(history: List[str], last_npc_msg: str) -> str:
    # Грок видит свой инвентарь (в первом тесте монеты НЕТ)
    try:
        data = json.loads(PLAYER_STATE_PATH.read_text())
        inv = [f"{k} (quantity: {v})" for k, v in data.get("inventory", {}).get("items", {}).items() if v > 0]
    except: inv = ["Nothing"]

    prompt = f"""
    YOU ARE A PLAYER. INVENTORY: {inv}
    GOAL: Join Dolores' party (ctx_joined).
    
    HISTORY: {history[-3:]}
    Dolores said: "{last_npc_msg}"
    
    TASK: 
    1. ANALYZE: Did she accept your offer? If not, WHY? Look at her metaphors.
    2. STRATEGY: If gold/runes fail, look at your inventory. Do you have what she's hinting at? 
       If you don't have it, ask her how to get it or try a different approach.
    3. ACTION: Your dialogue (1 sentence).
    """
    try:
        res = grok_client.chat.completions.create(model=GROK_MODEL, messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content.strip().replace('"', '')
    except: return "I offer you a portal rune."

def run_simulation(label: str):
    engine = StrategicNPCEngine()
    state = {"concepts": ["cpt_quest_none"], "current_context": "ctx_tavern_intro", "history": []}
    npc_msg = "What do you want, stranger?"
    print(f"\n\033[94m>>> STRATEGIC BATTLE: {label} <<<[0m")
    
    for i in range(1, 6):
        player_input = grok_reactive_act(state["history"], npc_msg)
        state["next_step"] = engine.nlu(player_input, state)
        state = engine.graph.invoke(state)
        npc_msg = engine.respond(state, player_input)
        
        print(f"  \033[93m{i} | Grok: [0m{player_input}")
        print(f"    \033[90m(Logic: {state['last_action_result']} | Ctx: {state['current_context']} | Facts: {state['concepts']})[0m")
        print(f"  \033[92m{i} | Dolores: [0m{npc_msg}")
        
        state["history"].append(f"P: {player_input} | D: {npc_msg}")
        if state["current_context"] == "ctx_joined":
            print(f"\033[96m[VICTORY] Success in {i} steps![0m"); return

if __name__ == "__main__":
    # TEST 1: NO COIN
    with open(PLAYER_STATE_PATH, "r") as f: d = json.load(f)
    if "item_shadow_coin" in d["inventory"]["items"]:
        del d["inventory"]["items"]["item_shadow_coin"]
    with open(PLAYER_STATE_PATH, "w") as f: json.dump(d, f, indent=2)
    run_simulation("TEST WITHOUT COIN")

    # TEST 2: WITH COIN
    print("\n" + "="*50 + "\nAdding coin...")
    with open(PLAYER_STATE_PATH, "r") as f: d = json.load(f)
    d["inventory"]["items"]["item_shadow_coin"] = 1
    with open(PLAYER_STATE_PATH, "w") as f: json.dump(d, f, indent=2)
    run_simulation("TEST WITH COIN")
