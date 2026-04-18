"""Utility functions for PDDL planning and diagnostics.

Note: planner execution now lives in `pddl_engines.py`; this module keeps
parsing helpers, validations, diagnostics, and a compatibility shim
`solve_with_unified_planning`.
"""

import re
from collections import deque
from pathlib import Path
from typing import List, Optional, Dict, Any, Set

UNIFIED_PLANNING_AVAILABLE = False
try:
    # Remove Aries engines before the UP environment is built; the Aries proto stubs
    # crash with newer protobuf versions and we don't use them.
    import unified_planning.engines.factory as _up_factory
    for _name in ("aries", "aries-val"):
        _up_factory.DEFAULT_ENGINES.pop(_name, None)
        if _name in _up_factory.DEFAULT_ENGINES_PREFERENCE_LIST:
            _up_factory.DEFAULT_ENGINES_PREFERENCE_LIST.remove(_name)

    from unified_planning.shortcuts import OneshotPlanner, get_environment
    from unified_planning.io import PDDLReader
    get_environment().credits_stream = None
    UNIFIED_PLANNING_AVAILABLE = True
except ImportError:
    OneshotPlanner = None
    get_environment = None
    PDDLReader = None

from . import logger
from ..logging_config import get_component_level
from ..world.player_state import PlayerState


def parse_init_state(problem_pddl: str) -> Dict[str, Any]:
    """Parse :init of problem into adjacency, blocked, objects, etc."""
    state = {
        'locations': {},
        'accessible': set(),
        'discovered': set(),
        'objects': set(),
        'paths': {}, # Adjacency list: loc -> list of neighbors
        'blocked': {} # Key: (from, to), Value: condition_obj
    }

    objects_match = re.search(r'\(:objects\s+(.+?)\)', problem_pddl, re.DOTALL)
    if objects_match:
        content = objects_match.group(1)
        clean_content = re.sub(r'-\s+[\w_-]+', '', content)
        state['objects'] = set(clean_content.split())
        logger.debug(f"Parsed {len(state['objects'])} objects from PDDL")

    at_matches = re.findall(r'\(at\s+([\w-]+)\s+([\w-]+)\)', problem_pddl)
    for obj, loc in at_matches:
        state['locations'][obj] = loc
        if obj.startswith('player'):
             state['locations']['player'] = loc

    acc_matches = re.findall(r'\(accessible\s+([\w-]+)\)', problem_pddl)
    state['accessible'] = set(acc_matches)

    disc_matches = re.findall(r'\(discovered\s+([\w-]+)\)', problem_pddl)
    state['discovered'] = set(disc_matches)
    
    path_matches = re.findall(r'\(path\s+([\w-]+)\s+([\w-]+)\)', problem_pddl)
    for l1, l2 in path_matches:
        if l1 not in state['paths']:
            state['paths'][l1] = []
        state['paths'][l1].append(l2)
        
    blocked_matches = re.findall(r'\(blocked\s+([\w-]+)\s+([\w-]+)\s+([\w-]+)\)', problem_pddl)
    for l1, l2, cond in blocked_matches:
        state['blocked'][(l1, l2)] = cond
        
    return state

def find_path_blockage(world_state: Dict[str, Any], player_state: PlayerState, start_loc: str, target_loc: str) -> Optional[str]:
    """BFS to detect physical connectivity and blockers."""
    logger.debug(f"Checking path blockage from '{start_loc}' to '{target_loc}'")
    if start_loc == target_loc:
        return None
        
    q_conn = deque([start_loc])
    v_conn = {start_loc}
    found_physically = False
    while q_conn:
        curr = q_conn.popleft()
        if curr == target_loc:
            found_physically = True
            break
        for neighbor in world_state['paths'].get(curr, []):
            if neighbor not in v_conn:
                v_conn.add(neighbor)
                q_conn.append(neighbor)

    if not found_physically:
        msg = f"No physical path found from '{start_loc}' to '{target_loc}' in the world graph."
        logger.debug(msg)
        return msg

    queue = deque([(start_loc, [])])
    visited = {start_loc}
    while queue:
        curr, path_edges = queue.popleft()
        if curr == target_loc:
            logger.debug(f"Physical path found: {path_edges}")
            for u, v in path_edges:
                if (u, v) in world_state['blocked']:
                    blocker = world_state['blocked'][(u, v)]
                    logger.debug(f"Edge ({u}, {v}) is blocked by {blocker}")
                    return f"Path is blocked between '{u}' and '{v}' by '{blocker}'."
            logger.debug("Physical path found and appears unblocked in 'blocked' predicates.")
            return None 
        for neighbor in world_state['paths'].get(curr, []):
            if neighbor not in visited:
                visited.add(neighbor)
                new_path = path_edges + [(curr, neighbor)]
                queue.append((neighbor, new_path))
                
    return "Path exists physically but might be logically complex."


def diagnose_planning_failure(domain_pddl: str, problem_pddl: str, player_state: Optional[PlayerState]) -> str:
    """Diagnose goal reachability and unmet preconditions (used on failure)."""
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
                obj_loc = world_state['locations'][target_obj]
                is_accessible = obj_loc in world_state['accessible']
                logger.debug(f"Target '{target_obj}' found at '{obj_loc}'. Accessible via teleport/frontier: {is_accessible}")
                if not is_accessible:
                    return f"Target '{target_obj}' is at '{obj_loc}', which is in the 'Fog of War' (not discovered/accessible yet)."
                blockages = find_path_blockage(world_state, player_state, world_state['locations'][player_state.player_id], obj_loc)
                if blockages:
                    return f"Cannot reach '{target_obj}': {blockages}"

        logger.debug(f"Checking predicate: {predicate_name}")
        relevant_actions = [a for a in actions if predicate_name in a['effects']]
        logger.debug(f"Relevant actions for '{predicate_name}': {[a['name'] for a in relevant_actions]}")
        if not relevant_actions:
            return f"No plan found – no actions achieve predicate '{predicate_name}'."
        
        for action in relevant_actions:
            logger.debug(f"Checking action '{action['name']}' with preconditions: {action['preconditions']}")
            issues = check_preconditions(action['precond_str'], player_state)
            logger.debug(f"Issues for '{action['name']}': '{issues}'")
            if issues:
                return f"No plan found because preconditions for action '{action['name']}' are not met: {issues}."
    
    return f"No plan found for goal '{goal_pddl}' – check reachability or complex interactions."


def parse_actions_from_domain(domain_pddl: str) -> List[Dict]:
    """Parse actions with preconditions/effects from domain string."""
    logger.debug(f"Domain contains '(:action': {'(:action' in domain_pddl}")
    logger.debug(f"Domain contains 'defeat': {'defeat' in domain_pddl}")
    logger.debug(f"Domain snippet around action: {domain_pddl[domain_pddl.find('(:action'):domain_pddl.find('(:action')+200]}")
    
    actions = []
    action_pattern = r'\(:action\s+(\w+)\s+:parameters\s+.*?\s+:precondition\s+(.*?)\s+:effect\s+(.*?)\s+\)'
    matches = re.findall(action_pattern, domain_pddl, re.DOTALL)
    logger.debug(f"Action matches found: {len(matches)}")
    for i, match in enumerate(matches):
        logger.debug(f"Match {i}: {match}")
        name, precond, effect = match
        actions.append({
            'name': name,
            'preconditions': parse_predicates(precond),
            'precond_str': precond,
            'effects': parse_predicates(effect)
        })
    return actions


def parse_predicates(pddl_block: str) -> List[str]:
    """Extract predicate names from a PDDL block."""
    return re.findall(r'\(\s*([\w-]+)', pddl_block)


def extract_predicates_from_goal(goal_pddl: str) -> List[List[str]]:
    """Extract predicates from goal block."""
    predicates = []
    pred_matches = re.findall(r'\(\s*([\w-]+)\s+([^)]+)\)', goal_pddl)
    for match in pred_matches:
        predicates.append([match[0], match[1].strip()])
    return predicates


def check_preconditions(precond_str: str, player_state: PlayerState) -> str:
    """Check abilities in preconditions against player_state."""
    missing_abilities = []
    ability_matches = re.findall(r'\(has-ability\s+[\w-]+\s+([\w-]+)\)', precond_str)
    player_abilities = getattr(player_state, 'abilities', {})
    for ab in ability_matches:
        if ab not in player_abilities:
            missing_abilities.append(ab)
    if missing_abilities:
        return f"missing required abilities ({', '.join(missing_abilities)})"
    return ""


def save_pddl_files(pddl_output_dir: Path, domain_pddl: str, problem_pddl: str, player_id: str = "player1") -> (str, str):
    """Save domain/problem PDDL to disk for debugging."""
    base_name = f"planning_{player_id}"
    domain_file = pddl_output_dir / f"{base_name}_domain.pddl"
    problem_file = pddl_output_dir / f"{base_name}_problem.pddl"
    
    logger.debug(f"Saving planning PDDL files: {domain_file}, {problem_file}")
    logger.debug(f"Resolved path: {domain_file.resolve()}")
    
    try:
        with open(domain_file, 'w', encoding='utf-8') as f:
            f.write(domain_pddl)
        logger.debug(f"Planning domain file saved: {domain_file}")
        
        with open(problem_file, 'w', encoding='utf-8') as f:
            f.write(problem_pddl)
        logger.debug(f"Planning problem file saved: {problem_file}")
        
    except Exception as e:
        logger.error(f"Failed to save planning PDDL files: {e} at {domain_file}")
        
    return str(domain_file), str(problem_file)


def solve_with_unified_planning(domain_pddl: str, problem_pddl: str) -> Optional[List[str]]:
    """Backward shim to UnifiedPlanningEngine for compatibility."""
    try:
        from npc_engine.engine.master.pddl_engines import UnifiedPlanningEngine
        return UnifiedPlanningEngine().solve(domain_pddl, problem_pddl)
    except Exception as e:
        logger.error(f"UnifiedPlanningEngine unavailable: {e}")
        return None


def extract_domain_predicates(domain_pddl: str) -> Dict[str, List[str]]:
    """Extract predicate definitions from domain."""
    predicates_map = {}
    start_idx = domain_pddl.find("(:predicates")
    if start_idx == -1:
        return {}
    count = 0
    end_idx = -1
    for i in range(start_idx, len(domain_pddl)):
        if domain_pddl[i] == '(':
            count += 1
        elif domain_pddl[i] == ')':
            count -= 1
            if count == 0:
                end_idx = i
                break
    if end_idx == -1:
        return {}
    pred_block = domain_pddl[start_idx:end_idx+1]
    matches = re.findall(r'\(([\w-]+)(.*?)\)', pred_block)
    for pred_name, args_str in matches:
        if pred_name == ":predicates": continue
        args = re.findall(r'\?[\w-]+', args_str)
        predicates_map[pred_name] = args
    return predicates_map


def validate_problem_predicates(domain_pddl: str, problem_pddl: str) -> Optional[str]:
    """Ensure init/goal predicates exist in domain."""
    domain_preds: Set[str] = set(extract_domain_predicates(domain_pddl).keys())
    ignore = {"and", "not", "forall", "exists", "imply"}
    unknown: Set[str] = set()

    def _collect(block: str):
        preds = parse_predicates(block)
        for p in preds:
            if p in ignore:
                continue
            if p not in domain_preds:
                unknown.add(p)

    # Use lookahead for :goal so the regex captures all init facts (greedy-safe)
    init_match = re.search(r"\(:init(.*?)(?=\s*\(:goal)", problem_pddl, re.DOTALL)
    if not init_match:
        # Fallback when :goal is absent — greedy match to the closing outer paren
        init_match = re.search(r"\(:init(.*)\)", problem_pddl, re.DOTALL)
    if init_match:
        _collect(init_match.group(1))

    goal_match = re.search(r"\(:goal(.*)\)\s*\)", problem_pddl, re.DOTALL)
    if not goal_match:
        goal_match = re.search(r"\(:goal(.*?)\)", problem_pddl, re.DOTALL)
    if goal_match:
        _collect(goal_match.group(1))

    if unknown:
        return f"Unknown predicates in problem: {sorted(unknown)}"
    return None


def extract_domain_types(domain_pddl: str) -> Set[str]:
    """Extract type names from the domain :types block (line by line, ignore comments)."""
    match = re.search(r"\(:types(.*?)\n\s*\)", domain_pddl, re.DOTALL)
    if not match:
        return set()
    raw = match.group(1)
    types: Set[str] = {"object"}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        # Remove inline comments
        if ";" in line:
            line = line.split(";", 1)[0].strip()
        if not line:
            continue
        # Split by '-' to strip supertypes; take tokens on the left
        left = line.split("-", 1)[0]
        for tok in left.split():
            if tok:
                types.add(tok)
    return types


def validate_problem_types(domain_pddl: str, problem_pddl: str) -> Optional[str]:
    """Ensure typed objects use only types declared in domain."""
    domain_types = extract_domain_types(domain_pddl)
    if not domain_types:
        return None

    problem_types_used: Set[str] = set()
    obj_block = re.search(r"\(:objects(.*?)\)", problem_pddl, re.DOTALL)
    if obj_block:
        for name, typ in re.findall(r"([\w-]+)\s*-\s*([\w-]+)", obj_block.group(1)):
            problem_types_used.add(typ)

    unknown = problem_types_used - domain_types
    if unknown:
        return f"Unknown types in problem: {sorted(unknown)}"
    return None
