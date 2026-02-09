# DAQS v5.0: PDDL Orchestrator Manual

## What it does
The orchestrator renders PDDL domains/problems (exploration + social), solves them via unified_planning, and feeds plans to the game/web UI. Persona/world data is injected from YAML into Jinja templates.

## Key pieces
- Templates: `npc_engine/config/logic/.../*.pddl.j2` with shared macros in `npc_engine/config/logic/macros.pddl.j2`.
- Renderer: `PDDLTemplateRenderer` centralizes Jinja env.
- Social assembler: `SocialWorldAssembler` builds objects/init facts from persona/world YAML (with pydantic validation).
- Planner: `MasterPlanner` uses `PlannerEngine` (unified_planning with fast-downward fallback).
- Validation: `validate_problem_predicates` fast-fails if init/goal uses predicates missing in the domain.

## Workflow (runtime)
1) Select mode: `exploration` or `social` based on goal/context.
2) Build domain:
   - Exploration: static domain file.
   - Social: `social_unified_v4.pddl.j2` rendered with persona constants (moods/tags/actions).
3) Build problem:
   - Exploration: `exploration/problem.pddl.j2` with typed objects and init facts from world graph/player state.
   - Social: `social/problem.pddl.j2` with contexts/concepts/triggers/traits/locks, plus dynamic state.
4) Validate PDDL (predicate presence) before solve.
5) Solve via `PlannerEngine` (unified_planning). On success, return plan; on failure, diagnostics logged.

## Templates and macros
- Use `macros.pddl.j2` for rendering typed objects and fact lists to avoid duplication.
- Keep predicates/types in domain aligned with facts generated in assemblers (traits, items, portals, etc.).

## Operational notes
- Debug logging in `world` component triggers PDDL dump to `generated/pddl/`.
- Persona/world YAML is validated when loaded; invalid payloads are logged and skipped.
- If planning fails with “Unknown predicates…”, the validator caught a mismatch between domain and problem.

## Extending
- New domain actions: add to domain template, update assemblers if new predicates needed, add minimal contract test in `tests/`.
- New planner engines: implement `PlannerEngine.solve`, wire into `MasterPlanner`.
- Caching: wrap renderer/solve inputs with hashing if repeated personas/goals become hot paths.
