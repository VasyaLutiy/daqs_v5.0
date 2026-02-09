"""Diagnostics utilities for planning failures (parsing, predicates, preconditions)."""

import re
from typing import List, Optional, Dict, Any

from . import logger
from ..world.player_state import PlayerState
from .planner_libs import (
    parse_actions_from_domain,
    extract_predicates_from_goal,
    check_preconditions,
    parse_init_state,
    find_path_blockage,
)


def diagnose_planning_failure(domain_pddl: str, problem_pddl: str, player_state: Optional[PlayerState]) -> str:
    """
    Diagnose why PDDL planning failed by analyzing the goal, domain actions, and player state.
    """
    if player_state is None:
        return "No plan found – player state not available for diagnosis."
    
    goal_match = re.search(r'\(:goal\s+(.+?)\)', problem_pddl, re.DOTALL)
    if not goal_match:
        return "Invalid problem format: no goal found."
    goal_pddl = goal_match.group(1).strip()
    if not goal_pddl.endswith(')'):
        goal_pddl += ')'
    logger.debug(f"Extracted goal_pddl: '{goal_pddl}'")
    
    world_state = parse_init_state(problem_pddl)
    logger.debug(f"World State Objects: {len(world_state['objects'])}")
    logger.debug(f"World State Locations: {world_state['locations']}")
    logger.debug(f"World State Accessible: {world_state['accessible']}")
    
    actions = parse_actions_from_domain(domain_pddl)
    logger.debug(f"Parsed actions: {[a['name'] for a in actions]}")
    
    goal_predicates = extract_predicates_from_goal(goal_pddl)
    logger.debug(f"Goal predicates: {goal_predicates}")
    
    for pred in goal_predicates:
        predicate_name = pred[0]
        args = pred[1].split()
        
        if len(args) > 1:
            target_obj = args[-1]
            if target_obj in world_state['locations']:
                start_loc = world_state['locations'].get('player', None) or next(iter(world_state['locations'].values()), None)
                blockage = find_path_blockage(world_state, player_state, start_loc, world_state['locations'][target_obj])
                if blockage:
                    return blockage

        relevant_actions = [a for a in actions if predicate_name in a['effects']]
        logger.debug(f"Checking predicate: {predicate_name}")
        logger.debug(f"Relevant actions for '{predicate_name}': {[a['name'] for a in relevant_actions]}")
        
        if not relevant_actions:
            return f"No actions achieve predicate '{predicate_name}'."
        
        for action in relevant_actions:
            issues = check_preconditions(action['precond_str'], player_state)
            logger.debug(f"Issues for '{action['name']}': '{issues}'")
            if issues:
                return f"Unmet preconditions for action '{action['name']}': {issues}"

    return "No plan found – check reachability or complex interactions."
