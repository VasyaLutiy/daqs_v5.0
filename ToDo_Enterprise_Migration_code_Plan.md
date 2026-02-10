# Enterprise Migration Plan (API-first)

## Goal
Make FastAPI the single source of planning/world logic. Streamlit becomes a thin client that calls HTTP endpoints.

## Steps

1) Backend endpoints (new, keep /process for compat)
   - `/health`: versions, engine availability, validation status.
   - `/world/state` (GET): input `player_id` & minimal state; output NPCs/exits/items/available quests.
   - `/plan/exploration` (POST): player_state + goal -> plan, quest_steps, diagnostics.
   - `/plan/social` (POST, optional): persona_id + social_state -> social plan/valid transitions.
- `/quest/difficulty` (POST): goal -> concept + plan length (uses UP).
- `/world/sync` (POST, optional): accept client state, return canonical state.
- `/social/init` (POST): persona metadata/start context so UI doesn’t load YAML locally.
- `/social/message` (POST): generate dialogue reply + update social_state (placeholder now).

2) Backend internals
   - Use existing orchestrator/planner; add validation before solve.
   - Add request_id, timings, engine name to logs.
   - Add fast-path for empty goal (return state only, skip planner).
   - Optional caches: PDDL render/parse per hash(persona, goal, world_version).

3) UI adjustments (feature-flagged)
   - HTTP client wrappers to call new endpoints.
   - Navigation uses `/world/state` (no planner call on goal=None).
   - Planning uses `/plan/exploration`; quest difficulty uses `/quest/difficulty`.
   - Remove direct `load_world/PDDLOrchestrator` usage after rollout.

4) Cleanup
   - Deprecate `/process` or make it proxy to `/plan/exploration`.
   - Drop sys.path hacks (done), ensure no local file access from UI.
   - Snapshot/contract tests for endpoints.

5) Branch/tag
   - Work on `v5.1_refactor`, keep main untouched.
