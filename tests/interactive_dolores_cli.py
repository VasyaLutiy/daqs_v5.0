"""
Interactive CLI to exercise Dolores' social PDDL flow.

Features:
- Loads persona/world data through SocialWorldAssembler
- Lets you fire triggers to gain concepts, unlock contexts, and shift contexts
- Can invoke the PDDL planner at any time with the current dynamic state

Notes:
- We seed the player with `cpt_quest_none` so the intro path can unlock.
- We add a missing forward edge from ctx_tavern_intro -> ctx_partnership to make the
  partnership route reachable for testing (without touching the source YAML).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from npc_engine.engine.master.pddl_orchestrator import PDDLOrchestrator
from npc_engine.engine.master.planner import MasterPlanner
from npc_engine.engine.master.pddl_libs import SocialWorldAssembler
from npc_engine.engine.logging_config import logging_manager
from npc_engine.engine.world.player_state import PlayerState

logger = logging_manager.get_component_logger('master')


EXTRA_CONNECTIONS: List[Tuple[str, str]] = [
    # Make partnership reachable for testing; does not persist to YAML
    ("ctx_tavern_intro", "ctx_partnership"),
]

# Map triggers to items to simulate inventory rewards
TRIGGER_ITEM_GAINS = {
    "trig_find_coin": "item_shadow_coin",
}


@dataclass
class DialogueState:
    current_context: str
    concepts: Set[str] = field(default_factory=set)
    visited: Set[str] = field(default_factory=set)
    exhausted_triggers: Set[str] = field(default_factory=set)
    unlocked: Set[str] = field(default_factory=set)
    hostile: bool = False
    mood: str | None = None
    items: Set[str] = field(default_factory=set)

    def to_dynamic_state(self) -> Dict:
        return {
            "current_context": self.current_context,
            "concepts": sorted(self.concepts),
            "visited_contexts": sorted(self.visited),
            "exhausted_triggers": sorted(self.exhausted_triggers),
            "unlocked_contexts": sorted(self.unlocked),
            "is_hostile": self.hostile,
            "current_mood": self.mood,
            "items": sorted(self.items),
        }


def build_world():
    assembler = SocialWorldAssembler(config_path=Path("npc_engine/config/social_world"), logger=logger)
    personas, target_atlas, target_persona = assembler.load_persona_bundle("persona_dolores")
    contexts, concepts, triggers = assembler.load_world_data(target_atlas, target_persona)
    assembler.apply_persona_overrides(contexts, "persona_dolores", personas)

    # Inject test-only edge to let us reach partnership in this sandbox harness
    for frm, to in EXTRA_CONNECTIONS:
        if frm in contexts:
            ctx = contexts[frm]
            ctx.setdefault("connections", [])
            if not any(c.get("to") == to for c in ctx["connections"]):
                ctx["connections"].append({"to": to, "direction": "forward"})

    return assembler, contexts, concepts, triggers, target_persona


def start_state(contexts: Dict[str, Dict]) -> DialogueState:
    start_ctx = next((cid for cid, c in contexts.items() if c.get("properties", {}).get("is_start")), None)
    if not start_ctx:
        start_ctx = list(contexts.keys())[0]
    state = DialogueState(current_context=start_ctx)
    # Seed baseline concept so the intro path can unlock
    state.concepts.add("cpt_quest_none")
    state.visited.add(start_ctx)
    return state


def list_actions(contexts, triggers):
    print("\nCommands:")
    print("  show                         - display current state")
    print("  triggers                     - list triggers in current context")
    print("  trigger <id>                 - fire trigger to gain its concept")
    print("  additem <item_id>            - add an item to inventory manually")
    print("  addconcept <concept_id>      - add a concept manually")
    print("  unlock <context_id>          - unlock a locked context if requirements met")
    print("  shift <context_id>           - move to a connected context")
    print("  mood <mood_id>               - set current mood (optional)")
    print("  plan                         - run PDDL planner with current state")
    print("  help                         - show commands")
    print("  quit                         - exit\n")


def print_state(state: DialogueState):
    print(f"\nContext: {state.current_context}")
    print(f"Concepts: {sorted(state.concepts)}")
    print(f"Items: {sorted(state.items)}")
    print(f"Visited: {sorted(state.visited)}")
    print(f"Unlocked: {sorted(state.unlocked)}")
    print(f"Exhausted triggers: {sorted(state.exhausted_triggers)}")
    if state.mood:
        print(f"Mood: {state.mood}")
    print("")


def triggers_in_context(current_context: str, triggers: Dict[str, Dict]) -> List[str]:
    available = []
    for tid, trig in triggers.items():
        if trig.get("parent_context") == current_context:
            available.append(f"{tid} -> yields {trig.get('yields')}")
    return available


def try_trigger(tid: str, state: DialogueState, triggers: Dict[str, Dict]):
    trig = triggers.get(tid)
    if not trig:
        print(f"Unknown trigger: {tid}")
        return
    if trig.get("parent_context") != state.current_context:
        print(f"Trigger {tid} not in current context.")
        return
    if tid in state.exhausted_triggers:
        print(f"Trigger {tid} already used.")
        return
    yields = trig.get("yields")
    if yields:
        state.concepts.add(yields)
        print(f"Added concept {yields}")
    # Simulate item gain if mapped
    gained_item = TRIGGER_ITEM_GAINS.get(tid)
    if gained_item:
        state.items.add(gained_item)
        print(f"Added item {gained_item}")
    state.exhausted_triggers.add(tid)


def try_unlock(target: str, state: DialogueState, contexts: Dict[str, Dict]):
    ctx = contexts.get(target)
    if not ctx:
        print(f"Unknown context: {target}")
        return
    props = ctx.get("properties", {})
    if not props.get("is_locked"):
        print(f"{target} is not locked.")
        return
    req = props.get("required_concept")
    combo = props.get("required_combo")
    if req and req not in state.concepts:
        print(f"Need concept {req} to unlock {target}")
        return
    if combo:
        if any(c not in state.concepts for c in combo):
            print(f"Need combo {combo} to unlock {target}")
            return
    state.unlocked.add(target)
    print(f"{target} unlocked.")


def connected_from(contexts: Dict[str, Dict], source: str) -> Set[str]:
    ctx = contexts.get(source) or {}
    conns = ctx.get("connections", []) or []
    targets = set()
    for conn in conns:
        target = conn.get("to")
        if target:
            targets.add(target)
            if conn.get("direction") == "bidirectional":
                targets.add(source)
    return targets


def try_shift(target: str, state: DialogueState, contexts: Dict[str, Dict]):
    targets = connected_from(contexts, state.current_context)
    if target not in targets:
        print(f"{target} is not connected from {state.current_context}")
        return
    target_props = contexts.get(target, {}).get("properties", {})
    if target_props.get("is_locked") and target not in state.unlocked:
        print(f"{target} is locked. Unlock first.")
        return
    state.current_context = target
    state.visited.add(target)
    print(f"Shifted to {target}")


def run_planner(state: DialogueState):
    orch = PDDLOrchestrator()
    planner = MasterPlanner()
    ps = PlayerState(player_id="tester")
    # Populate inventory for planning if any items were gathered
    for item_id in state.items:
        ps.inventory.add_item(item_id)
    domain, problem = orch.generate(
        mode="social",
        player_state=ps,
        world_graph=None,
        goal_pddl="(visited ctx_joined)",
        dynamic_state=state.to_dynamic_state(),
        active_persona="persona_dolores",
    )
    plan, diag = planner.solve(domain, problem, player_id="tester", player_state=ps)
    if plan:
        print("Plan:")
        for step in plan:
            print(f"  - {step}")
    else:
        print(f"No plan. Diagnostic: {diag}")


def main():
    assembler, contexts, concepts, triggers, target_persona = build_world()
    state = start_state(contexts)
    list_actions(contexts, triggers)
    while True:
        cmd = input("dolores> ").strip()
        if not cmd:
            continue
        parts = cmd.split()
        action = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None

        if action == "quit" or action == "exit":
            break
        if action == "help":
            list_actions(contexts, triggers)
        elif action == "show":
            print_state(state)
        elif action == "triggers":
            avail = triggers_in_context(state.current_context, triggers)
            print("\n".join(avail) if avail else "No triggers here.")
        elif action == "trigger" and arg:
            try_trigger(arg, state, triggers)
        elif action == "unlock" and arg:
            try_unlock(arg, state, contexts)
        elif action == "shift" and arg:
            try_shift(arg, state, contexts)
        elif action == "plan":
            run_planner(state)
        elif action == "mood" and arg:
            state.mood = arg
            print(f"Mood set to {arg}")
        elif action == "additem" and arg:
            state.items.add(arg)
            print(f"Item added: {arg}")
        elif action == "addconcept" and arg:
            state.concepts.add(arg)
            print(f"Concept added: {arg}")
        else:
            print("Unknown command. Type 'help' for options.")


if __name__ == "__main__":
    main()
