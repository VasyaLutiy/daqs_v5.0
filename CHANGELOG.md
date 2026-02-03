# Changelog: DAQS Fresh Edition

## [5.6.0] - 2026-01-15
### Added
- **Architectural Refactoring**: Introduced `PDDLOrchestrator` to centralize and decouple PDDL domain/problem generation from the API layer.
- **Integrated Social Planning**: The `/process` endpoint now automatically detects and handles Social Mode goals using `PDDLOrchestrator`.
- **Mission Board (Quest Menu)**: Restored dynamic quest listing in `social_webui.py`, allowing players to preview plans and briefings before accepting.
- **Dynamic Quest Briefings**: Added `assemble_quest_giver` to `PromptOrchestrator` for translating raw PDDL plans into character-driven narrative instructions.
- **Persistence Layer**: Implemented official quest acceptance that saves the goal to `player_state.json` and transitions the UI to World Mode.

### Changed
- **Recursive Resource Loading**: Updated both `PromptOrchestrator` and `PDDLOrchestrator` to use `rglob` for loading YAML nodes, ensuring compatibility with hierarchical Regional Atlases.
- **PDDL Templates**: Migrated to Jinja2 templates for more flexible and maintainable PDDL problem generation.

### Fixed
- **Nested Item Visibility**: Fixed a bug where items inside Atlas YAMLs were invisible to the quest generator; added a global promotion pass in `loader.py`.
- **Predicate Speech Bug**: Fixed an issue where NPCs would speak using PDDL IDs (e.g., `ctx_axiom`) by ensuring proper ID resolution in the narrative orchestrator.
- **Available Quests Logic**: Standardized quest generation to always include available items in metadata, regardless of the current goal.

## [5.5.0] - 2026-01-14
### Added
- **Object-Oriented Portal Logic (v5.6 Prototype)**: Portals are no longer just edge types; they are now interactive World Objects.
- **Advanced PDDL Teleportation**: Introduced the `teleport` action in the world domain. It requires a player to be at a Portal Object and possess a specific key to instantly move to a target location.
- **Hierarchical Portal Discovery**: The `loader.py` now automatically detects portal objects within Atlas YAMLs and generates virtual navigation edges for the Oracle and Planner.
- **Universal Oracle (BFS v2)**: Re-engineered the pathfinding logic in `engine_core.py` to be robust against hierarchical structures and bidirectional links.
- **Automated World Migration**: Consistently merged all loose world nodes into high-level Regional Atlases.

### Fixed
- **PDDL Goal Mismatch**: Standardized the use of `(at player_001 ...)` predicates for goal validation.
- **Recursive Edge Detection**: Fixed a bug where the Oracle was "blind" to bidirectional paths not explicitly defined in the local node.
- **NLU Hallucination Guard**: Added strict `.strip()` and type-checking for PDDL actions returned by the LLM.

## [5.4.0] - 2026-01-13
### Added
- **Strict Quest Logic**: Re-engineered the PDDL generator to enforce physical rules, requiring explicit `pickup` and `unlock` actions.
- **Hierarchical PDDL Mapping**: The engine now correctly maps items and NPCs embedded within Atlas YAMLs into the symbolic world state.
