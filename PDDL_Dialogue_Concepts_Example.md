## NeuroSymbolic Dialogue Guardrails (Dolores Shadow/Partnership Flow)

This describes how the Dolores dialogue uses NeuroSymbolic control to prevent LLM hallucinations and to ensure combo-locked flows (e.g., `ctx_shadow_entry`) work end-to-end.

### Core Evidence (Deterministic Chain)
- **Structured source of truth**: Persona YAML (`npc_engine/config/social_world/nodes/personas/elves.yaml`), PDDL templates (`npc_engine/config/logic/social/social_unified_v4.pddl.j2`), and the runtime state (concepts, visited, unlocked, inventory).
- **Allowed moves only**: `MoveValidator` derives valid actions from current graph/locks/concepts. The LLM can propose, but only allowed moves execute; others are ignored.
- **Deterministic mutations**: `StateManager` handlers update state for each action type. No free-form world edits—every state change is a small, auditable function.
- **Formal planner**: Orchestrator regenerates domain/problem from deterministic state + YAML. Planner (unified_planning/Fast Downward) solves against formal PDDL; it cannot fabricate items/contexts not in state.
- **No long LLM memory needed**: Prompts are rebuilt each turn from state; the authoritative “history” is the structured state, not prior LLM messages.

### Key Fixes/Enablers
- **Combo unlocks**: `apply-combo-concept` action added to `social_unified_v4.pddl.j2`, and handled in `StateManager`. `(requires-combo …)` is now satisfiable in planning and runtime.
- **Dialogue-earned items**: `PDDLOrchestrator` now ingests `dynamic_state["items"]` into problem objects and `(has-item …)` facts. Triggers (e.g., `trig_find_coin`) can grant both concepts and items, and the planner sees them.

### Flow Diagram (Text)
```
User utterance
   ↓
LLM (NLU intent) → Proposed action
   ↓ (filtered)
MoveValidator (allowed moves from graph + state)
   ↓ (valid)
StateManager (deterministic update: concepts/visited/unlocked/mood/items)
   ↓
Orchestrator (build PDDL domain/problem from YAML + state)
   ↓
PDDL Planner (unified_planning/Fast Downward)
   ↓
Plan / Next moves → UI/Narrative
```

### Dolores Shadow Path (Hard Evidence)
- Concepts required: `cpt_shadow_rumor` (from `trig_listen_rumors`) + `cpt_shadow_token` (from `trig_find_coin`, also grants `item_shadow_coin` in tests).
- Lock: `ctx_shadow_entry` has `required_combo: [cpt_shadow_rumor, cpt_shadow_token]`.
- Action: `apply-combo-concept` now exists in domain and state handler. Logs show execution:
  - `[NLU Action] apply-combo-concept player ctx_neutral_talk ctx_shadow_entry cpt_shadow_rumor cpt_shadow_token`
  - `StateManager: Combo unlock and shift to ctx_shadow_entry`
- Shift: `shift-context ctx_shadow_entry ctx_shadow_deal` works; mood induction to `serious` confirmed in logs.

### Partnership Path (Goal `ctx_joined`)
- `trig_hire_companion` → `cpt_partnership_offer` → `apply-concept` unlocks `ctx_partnership` → `trig_accept_partnership` → `cpt_agreement` → unlock/shift `ctx_joined`.
- Planner sees these because required concepts and unlocked contexts are explicit in state and PDDL.

### Why Hallucinations Are Contained
- Allowed-move gating: invalid/unsupported actions are dropped.
- Deterministic handlers: only named handlers mutate state.
- Planner as arbiter: plans only over formal predicates/objects generated from state/YAML.
- Templates from YAML: no ad-hoc LLM-created symbols; items/concepts must exist in YAML or dynamic state.
- Rebuilt prompts each turn: no reliance on LLM message history for consistency.

### Test Harness Notes
- `tests/interactive_dolores_cli.py`: CLI to exercise triggers, locks, moods, planner. Command `trigger trig_find_coin` grants both `cpt_shadow_token` and `item_shadow_coin`; `plan` shows `(has-item tester item_shadow_coin)` in PDDL.
- Injected test-only edge `ctx_tavern_intro -> ctx_partnership` in CLI to explore partnership path; source YAML untouched.

### Conclusion
The system’s guarantees come from: (1) explicit allowed actions, (2) deterministic state updates, (3) PDDL planner over structured state/YAML, and (4) per-turn prompt regeneration from state. This architecture keeps the LLM from inventing world changes and proves NeuroSymbolic control over dialogue progression.
