from pathlib import Path
from typing import Dict, Any, List, Optional, Set
import yaml

try:
    from langgraph.graph import StateGraph, END
except ImportError:
    raise SystemExit("langgraph not installed. pip install langgraph")

CONFIG_PATH = Path("npc_engine/config/social_world/nodes/personas/elves.yaml")
PERSONA_ID = "persona_dolores"

def load_persona(persona_id: str) -> Dict[str, Any]:
    data = yaml.safe_load(CONFIG_PATH.read_text())
    for p in data.get("personas", []):
        if p.get("id") == persona_id:
            return p
    raise ValueError("Persona not found")

def build_graph(persona: Dict[str, Any]) -> Any:
    sg = StateGraph(dict)
    contexts = {c["id"]: c for c in persona.get("contexts", [])}
    triggers = {t["id"]: t for t in persona.get("triggers", [])}
    
    def make_ctx_handler(ctx_id: str):
        def handler(state: Dict[str, Any]):
            new_state = state.copy()
            new_state["current_context"] = ctx_id
            prov = contexts[ctx_id].get("properties", {}).get("provides_concept")
            if prov:
                c = set(new_state.get("concepts", []))
                if prov not in c:
                    print(f"  [Action] Context {ctx_id} provided: {prov}")
                    c.add(prov)
                    new_state["concepts"] = list(c)
            print(f"[Node] === {contexts[ctx_id].get('name', ctx_id)} ===")
            return new_state
        return handler

    for cid in contexts:
        sg.add_node(cid, make_ctx_handler(cid))

    def make_trigger_handler(tid: str, yields: str):
        def handler(state: Dict[str, Any]):
            new_state = state.copy()
            c = set(new_state.get("concepts", []))
            c.add(yields)
            new_state["concepts"] = list(c)
            print(f"  [Trigger] {tid} -> Added knowledge: {yields}")
            return new_state
        return handler

    for tid, trig in triggers.items():
        yields = trig.get("yields")
        parent = trig.get("parent_context")
        if yields and parent:
            sg.add_node(tid, make_trigger_handler(tid, yields))
            sg.add_edge(tid, parent)

    def check_access(ctx_id: str, current_concepts: List[str]) -> bool:
        props = contexts[ctx_id].get("properties", {})
        if not props.get("is_locked", False): return True
        req_c = props.get("required_concept")
        if req_c and req_c not in current_concepts: return False
        req_combo = props.get("required_combo", [])
        if req_combo and not all(c in current_concepts for c in req_combo): return False
        return True

    for cid, ctx in contexts.items():
        targets = [conn["to"] for conn in ctx.get("connections", [])]
        relevant_triggers = [tid for tid, t in triggers.items() if t.get("parent_context") == cid]
        
        def router(state: Dict[str, Any], cid=cid, targets=targets, triggers_list=relevant_triggers):
            concepts = state.get("concepts", [])
            goal = state.get("target_goal")
            
            if cid == goal:
                print(f"  [Router] SUCCESS: Goal reached.")
                return END

            # ПРИОРИТЕТ 1: Использовать триггеры, если они дают новые концепты
            for tid in triggers_list:
                yielded = triggers[tid].get("yields")
                if yielded not in concepts:
                    print(f"  [Router] New info via trigger: {tid}")
                    return tid
            
            # ПРИОРИТЕТ 2: Идти в закрытые контексты, если они теперь открыты
            for t in targets:
                if contexts[t].get("properties", {}).get("is_locked") and check_access(t, concepts):
                    print(f"  [Router] Moving forward to unlocked {t}")
                    return t

            # ПРИОРИТЕТ 3: Обычные пути
            for t in targets:
                if check_access(t, concepts):
                    if t == "ctx_tavern_intro" and len(concepts) > 2: continue 
                    print(f"  [Router] Path to {t}")
                    return t
            
            for t in targets:
                if check_access(t, concepts): return t

            print(f"  [Router] STUCK in {cid}")
            return END

        path_map = {t: t for t in targets}
        for tr in relevant_triggers: path_map[tr] = tr
        path_map[END] = END
        sg.add_conditional_edges(cid, router, path_map)

    start_ctx = next((c["id"] for c in persona.get("contexts", []) if c.get("properties", {}).get("is_start")), "ctx_tavern_intro")
    sg.set_entry_point(start_ctx)
    return sg.compile()

if __name__ == "__main__":
    persona = load_persona(PERSONA_ID)
    app = build_graph(persona)
    
    initial_state = {
        "concepts": ["cpt_quest_none"],
        "target_goal": "ctx_joined", 
        "current_context": None,
    }
    
    print(f"--- Simulation: {persona['name']} ---\n")
    try:
        result = app.invoke(initial_state, config={"recursion_limit": 30})
        print(f"\nFinal State: {result['current_context']}")
        print(f"Concepts: {result['concepts']}")
    except Exception as e:
        print(f"\nSimulation ended: {e}")