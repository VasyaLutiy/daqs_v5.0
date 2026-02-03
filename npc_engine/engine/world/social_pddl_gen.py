import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional

class SocialPDDLGenerator:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.contexts = {}
        self.concepts = {}
        self.triggers = {}
        
    def load_world(self):
        # 1. Load Contexts
        ctx_dir = self.config_dir / "nodes" / "contexts"
        if ctx_dir.exists():
            for f in ctx_dir.glob("*.yaml"):
                data = yaml.safe_load(f.read_text())
                self.contexts[data['id']] = data
        
        print(f"DEBUG: Loaded contexts: {list(self.contexts.keys())}")
                
        # 2. Load Concepts
        cpt_dir = self.config_dir / "nodes" / "concepts"
        if cpt_dir.exists():
            for f in cpt_dir.glob("*.yaml"):
                data = yaml.safe_load(f.read_text())
                self.concepts[data['id']] = data

        # 3. Load Triggers
        trig_dir = self.config_dir / "nodes" / "triggers"
        if trig_dir.exists():
            for f in trig_dir.glob("*.yaml"):
                data = yaml.safe_load(f.read_text())
                self.triggers[data['id']] = data

    def generate_problem(self, player_id: str, goal_context_id: str, dynamic_state: Dict[str, Any] = None) -> str:
        objects = []
        init = []
        
        # 1. Define Objects
        objects.extend([f"{cid} - context" for cid in self.contexts])
        objects.extend([f"{cid} - concept" for cid in self.concepts])
        objects.extend([f"{tid} - trigger" for tid in self.triggers])
        objects.append(f"{player_id} - agent")
        
        # 2. Init State (Static)
        
        # Context Connections & Locks
        for cid, ctx in self.contexts.items():
            props = ctx.get('properties', {})
            
            # Links
            for conn in ctx.get('connections', []):
                target = conn['to']
                init.append(f"(connected {cid} {target})")
                if conn.get('direction') == 'bidirectional':
                    init.append(f"(connected {target} {cid})")
            
            # Locks
            # If logic: locked only if NOT already unlocked in dynamic state
            if props.get('is_locked'):
                 # Simple check: if dynamic state says it's unlocked, skip.
                 # For now, let's assume PDDL handles unlocking via apply-concept action sequence.
                 # But if we want persistence, we need to check dynamic_state['unlocked_contexts']
                 is_unlocked = dynamic_state and cid in dynamic_state.get('unlocked_contexts', [])
                 if not is_unlocked:
                     init.append(f"(locked {cid})")
            
            # Requirements
            if props.get('required_concept'):
                init.append(f"(requires-concept {cid} {props['required_concept']})")
                
            if props.get('required_combo'):
                combo = props['required_combo']
                if len(combo) == 2:
                    init.append(f"(requires-combo {cid} {combo[0]} {combo[1]})")
                
            # Passive Concept Provision
            if props.get('provides_concept'):
                init.append(f"(provides-concept {cid} {props['provides_concept']})")

        # Triggers placement
        for tid, trig in self.triggers.items():
            parent = trig.get('parent_context')
            if parent:
                init.append(f"(in-context {tid} {parent})")
            
            yields = trig.get('yields')
            if yields:
                init.append(f"(trigger-yields {tid} {yields})")

        # 3. Dynamic State Injection
        if dynamic_state:
            curr = dynamic_state.get("current_context")
            if curr:
                init.append(f"(active-context {player_id} {curr})")
            
            for cpt in dynamic_state.get("concepts", []):
                init.append(f"(has-concept {player_id} {cpt})")
                
            for v_ctx in dynamic_state.get("visited_contexts", []):
                init.append(f"(visited {v_ctx})")
                
            for exh_trig in dynamic_state.get("exhausted_triggers", []):
                init.append(f"(exhausted {exh_trig})")
        else:
            # Fallback Start
            start_ctx = next((cid for cid, c in self.contexts.items() if c.get('properties', {}).get('is_start')), None)
            if start_ctx:
                init.append(f"(active-context {player_id} {start_ctx})")
        
        # 4. Construct PDDL
        pddl = f"""(define (problem narrative-journey)
  (:domain narrative-flow)
  (:objects
    {" ".join(objects)}
  )
  (:init
    {" ".join(init)}
  )
  (:goal
    (visited {goal_context_id})
  )
)"""
        return pddl