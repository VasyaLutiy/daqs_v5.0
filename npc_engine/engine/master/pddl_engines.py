"""Planner engine implementations (unified_planning and future adapters).

Responsibilities:
- Parse domain/problem via unified_planning
- Select and run planner engines (fast-downward fallback to default)
- Return plans as string actions
"""

from typing import List, Optional

from npc_engine.engine.master import logger

try:
    import unified_planning.engines.factory as _up_factory
    from unified_planning.shortcuts import OneshotPlanner, get_environment
    from unified_planning.io import PDDLReader
    get_environment().credits_stream = None
    for _name in ("aries", "aries-val"):
        _up_factory.DEFAULT_ENGINES.pop(_name, None)
        if _name in _up_factory.DEFAULT_ENGINES_PREFERENCE_LIST:
            _up_factory.DEFAULT_ENGINES_PREFERENCE_LIST.remove(_name)
    _UP_AVAILABLE = True
except ImportError:
    OneshotPlanner = None  # type: ignore
    PDDLReader = None  # type: ignore
    _UP_AVAILABLE = False


class PlannerEngine:
    """Interface for planner engines."""

    def solve(self, domain_pddl: str, problem_pddl: str) -> Optional[List[str]]:
        raise NotImplementedError


class UnifiedPlanningEngine(PlannerEngine):
    """Wrapper around unified_planning solve with built-in fallback."""

    def solve(self, domain_pddl: str, problem_pddl: str) -> Optional[List[str]]:
        if not _UP_AVAILABLE or OneshotPlanner is None or PDDLReader is None:
            logger.error("Unified Planning library is not available.")
            return None

        try:
            logger.debug("Parsing PDDL with unified_planning")
            reader = PDDLReader()
            problem = reader.parse_problem_string(domain_pddl, problem_pddl)
            logger.debug(f"Parsed problem with {len(problem.actions)} actions")
        except Exception as e:
            logger.error(f"Error parsing PDDL via unified_planning: {e!r}")
            return None

        planners = []
        try:
            planners.append(OneshotPlanner(problem_kind=problem.kind, name="fast-downward"))
            logger.debug("Fast Downward planner available via unified_planning")
        except Exception as e:
            logger.warning(f"Fast Downward unavailable, falling back to default planner. ({e.__class__.__name__})")

        if not planners:
            try:
                planners.append(OneshotPlanner(problem_kind=problem.kind))
                logger.debug("Default unified_planning planner initialized")
            except Exception as e:
                logger.error(f"No unified_planning planner could be initialized: {e!r}")
                return None

        result = None
        for planner in planners:
            try:
                logger.debug(f"Calling planner via unified_planning: {planner}")
                result = planner.solve(problem)  # type: ignore[attr-defined]
                break
            except Exception as e:
                logger.error(f"Planner solve failed with {e.__class__.__name__}: {e!r}")
                result = None
                continue

        if result is None:
            logger.error("All planners failed to produce a result.")
            return None

        if result.plan:
            plan_steps = []
            for action in result.plan.actions:
                action_str = f"{action.action.name}"
                if action.actual_parameters:
                    params = " ".join(str(p) for p in action.actual_parameters)
                    action_str += f" {params}"
                plan_steps.append(action_str)
            logger.debug(f"Extracted {len(plan_steps)} plan steps")
            return plan_steps

        logger.warning("No plan found by unified_planning")
        return None
