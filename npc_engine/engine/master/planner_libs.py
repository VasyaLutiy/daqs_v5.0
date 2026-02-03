"""Utility functions for PDDL planning and diagnostics."""

import re
from pathlib import Path
from typing import List, Optional, Dict, Any

# Move imports to the top
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
    """
    Parse the :init section of the PDDL problem to extract world state.

    Args:
        problem_pddl (str): The PDDL problem string.

    Returns:
        Dict[str, Any]: A dictionary containing:
            - 'locations': Dict[str, str] mapping object_id -> location_id (from 'at' predicates).
            - 'accessible': Set[str] of location IDs marked as accessible.
            - 'discovered': Set[str] of location IDs marked as discovered.
            - 'objects': Set[str] of all defined object IDs.
    """
    state = {
        'locations': {},
        'accessible': set(),
        'discovered': set(),
        'objects': set(),
        'paths': {}, # Adjacency list: loc -> list of neighbors
        'blocked': {} # Key: (from, to), Value: condition_obj
    }

    # Extract objects
    objects_match = re.search(r'\(:objects\s+(.+?)\)', problem_pddl, re.DOTALL)
    if objects_match:
        content = objects_match.group(1)
        clean_content = re.sub(r'-\s+[\w_-]+', '', content)
        state['objects'] = set(clean_content.split())
        logger.debug(f"Parsed {len(state['objects'])} objects from PDDL")

    # Extract init facts - search entire string to avoid parenthesis nesting issues
    # Parse (at obj loc) - updated regex to include hyphens
    at_matches = re.findall(r'\(at\s+([\w-]+)\s+([\w-]+)\)', problem_pddl)
    for obj, loc in at_matches:
        state['locations'][obj] = loc
        # Also track player location explicitly if found (heuristic)
        if obj.startswith('player'):
             state['locations']['player'] = loc

    # Parse (accessible loc)
    acc_matches = re.findall(r'\(accessible\s+([\w-]+)\)', problem_pddl)
    state['accessible'] = set(acc_matches)

    # Parse (discovered loc)
    disc_matches = re.findall(r'\(discovered\s+([\w-]+)\)', problem_pddl)
    state['discovered'] = set(disc_matches)
    
    # Parse (path from to)
    path_matches = re.findall(r'\(path\s+([\w-]+)\s+([\w-]+)\)', problem_pddl)
    for l1, l2 in path_matches:
        if l1 not in state['paths']: state['paths'][l1] = []
        state['paths'][l1].append(l2)
        
    # Parse (blocked from to condition)
    blocked_matches = re.findall(r'\(blocked\s+([\w-]+)\s+([\w-]+)\s+([\w-]+)\)', problem_pddl)
    for l1, l2, cond in blocked_matches:
        state['blocked'][(l1, l2)] = cond
        
    return state

def find_path_blockage(world_state: Dict[str, Any], player_state: PlayerState, start_loc: str, target_loc: str) -> Optional[str]:
    """
    Perform BFS to find if a path exists and what blocks it.
    Returns a string description of the blockage or None if path is clear/non-existent logic.
    """
    logger.debug(f"Checking path blockage from '{start_loc}' to '{target_loc}'")
    if start_loc == target_loc:
        return None
        
    queue = [(start_loc, [])] # current, path_history
    visited = set()
    
    # 1. Check if physically connected (ignoring blocks)
    found_physically = False
    
    # Simple BFS for connectivity
    q_conn = [start_loc]
    v_conn = {start_loc}
    while q_conn:
        curr = q_conn.pop(0)
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

    # 2. Find blocking condition on the shortest path
    # BFS again, but track edges
    queue = [(start_loc, [])] # loc, list of (u, v) edges
    visited = {start_loc}
    
    while queue:
        curr, path_edges = queue.pop(0)
        
        if curr == target_loc:
            # We found a path. Now check if any edge in it is blocked.
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
    """
    Diagnose why PDDL planning failed by analyzing the goal, domain actions, and player state.
    """
    if player_state is None:
        return "No plan found – player state not available for diagnosis."
    
    # Extract goal from problem_pddl
    goal_match = re.search(r'\(:goal\s+(.+?)\)', problem_pddl, re.DOTALL)
    
    if not goal_match:
        return "Invalid problem format: no goal found."
    goal_pddl = goal_match.group(1).strip()
    if not goal_pddl.endswith(')'):
        goal_pddl += ')'
    logger.debug(f"Extracted goal_pddl: '{goal_pddl}'")
    
    # Parse initial state for advanced diagnostics
    world_state = parse_init_state(problem_pddl)
    logger.debug(f"World State Objects: {len(world_state['objects'])}")
    logger.debug(f"World State Locations: {world_state['locations']}")
    logger.debug(f"World State Accessible: {world_state['accessible']}")
    
    # Parse actions from domain_pddl
    actions = parse_actions_from_domain(domain_pddl)
    logger.debug(f"Parsed actions: {[a['name'] for a in actions]}")
    
    # Simple goal parsing
    goal_predicates = extract_predicates_from_goal(goal_pddl)
    logger.debug(f"Goal predicates: {goal_predicates}")
    
    for pred in goal_predicates:
        predicate_name = pred[0]
        args = pred[1].split()
        
        # --- Advanced Diagnostics: Object Existence & Reachability ---
        # Check if goal involves an object (e.g., has-item player artifact)
        # Arguments usually: ?player ?target
        if len(args) > 1:
            target_obj = args[-1] # Assume last arg is target (e.g., artifact, enemy)
            
            # 1. Check if object exists in the problem
            if target_obj not in world_state['objects'] and target_obj != player_state.player_id:
                # Might be a location or type, skip if not sure, but good heuristic
                pass 

            # 2. Check Reachability (for items/NPCs)
            if target_obj in world_state['locations']:
                obj_loc = world_state['locations'][target_obj]
                is_accessible = obj_loc in world_state['accessible']
                logger.debug(f"Target '{target_obj}' found at '{obj_loc}'. Accessible via teleport/frontier: {is_accessible}")
                
                if not is_accessible:
                    return f"Target '{target_obj}' is at '{obj_loc}', which is in the 'Fog of War' (not discovered/accessible yet)."
                
                # If it IS accessible but no plan found, check for Blocked Paths logic
                # We do a mini-BFS to see if path exists but is blocked
                blockages = find_path_blockage(world_state, player_state, world_state['locations'][player_state.player_id], obj_loc)
                if blockages:
                    return f"Cannot reach '{target_obj}': {blockages}"

        # --- End Advanced Diagnostics ---

        logger.debug(f"Checking predicate: {predicate_name}")
        # Find actions that achieve this predicate
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
    """
    Parse action definitions from a PDDL domain string using regex.

    Extracts action names, preconditions, and effects from the domain for diagnostic purposes.
    This is a simplified parser focused on key components needed for failure analysis.

    Args:
        domain_pddl (str): The full PDDL domain string.

    Returns:
        List[Dict]: A list of dictionaries, each representing an action with keys:
            - 'name' (str): The action name (e.g., 'move').
            - 'preconditions' (List[str]): List of predicate names in preconditions.
            - 'precond_str' (str): The full precondition string for detailed checking.
            - 'effects' (List[str]): List of predicate names in effects.

    Raises:
        None: Regex parsing may fail silently if the domain format is unexpected, logging debug info.

    Examples:
        >>> domain = "(:action move :parameters (?p) :precondition (at ?p loc) :effect (at ?p new_loc))"
        >>> actions = parse_actions_from_domain(domain)
        >>> actions[0]['name']
        'move'
    """
    logger.debug(f"Domain contains '(:action': {'(:action' in domain_pddl}")
    logger.debug(f"Domain contains 'defeat': {'defeat' in domain_pddl}")
    logger.debug(f"Domain snippet around action: {domain_pddl[domain_pddl.find('(:action'):domain_pddl.find('(:action')+200]}")
    
    actions = []
    # Updated regex: Allow optional spaces after :precondition and :effect
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
    """
    Extract predicate names from a PDDL block (e.g., preconditions or effects).

    Uses regex to find all predicate names (e.g., 'at', 'has-ability') in a given PDDL string segment.
    Handles hyphenated predicates like 'has-ability'.

    Args:
        pddl_block (str): A substring of PDDL containing predicates, such as "(and (at ?p loc) (has-ability ?p stealth))".

    Returns:
        List[str]: A list of predicate names found in the block (e.g., ['and', 'at', 'has-ability']).

    Raises:
        None: Regex may not match malformed PDDL, but no exceptions are raised.

    Examples:
        >>> block = "(and (at player forest) (has-ability player stealth))"
        >>> parse_predicates(block)
        ['and', 'at', 'has-ability']
    """
    return re.findall(r'\(\s*([\w-]+)', pddl_block)


def extract_predicates_from_goal(goal_pddl: str) -> List[List[str]]:
    """
    Extract predicates from a PDDL goal string.
    """
    predicates = []
    # Updated regex to handle hyphens in predicate names (e.g., has-item)
    pred_matches = re.findall(r'\(\s*([\w-]+)\s+([^)]+)\)', goal_pddl)
    for match in pred_matches:
        predicates.append([match[0], match[1].strip()])
    return predicates


def check_preconditions(precond_str: str, player_state: PlayerState) -> str:
    """
    Check if the player meets the preconditions of an action, focusing on abilities.

    Parses the precondition string for 'has-ability' predicates and verifies if the player has
    the required abilities. Currently checks abilities; can be extended for other preconditions
    like location or inventory.

    Args:
        precond_str (str): The full precondition string from the action, e.g., "(and (at ?p loc) (has-ability ?p combat))".
        player_state (PlayerState): The player's current state, including abilities.

    Returns:
        str: A string describing unmet preconditions (e.g., "missing required abilities (combat, magic)"),
            or an empty string if all checked preconditions are met.

    Raises:
        None: Assumes player_state is valid; logs debug info.

    Examples:
        >>> precond = "(and (at ?p loc) (has-ability ?p combat))"
        >>> player = PlayerState(player_id="test")
        >>> player.add_ability("stealth", 1)
        >>> check_preconditions(precond, player)
        'missing required abilities (combat)'
    """
    player_abilities = list(player_state.abilities.keys())
    logger.debug(f"Player abilities: {player_abilities}")
    
    # Extract required abilities from has-ability predicates
    ability_matches = re.findall(r'\(has-ability \?p (\w+)\)', precond_str)
    required_abilities = list(set(ability_matches))
    logger.debug(f"Required abilities for action: {required_abilities}")
    
    if required_abilities and not any(ability in player_abilities for ability in required_abilities):
        return f"missing required abilities ({', '.join(required_abilities)})"
    
    return ""


def save_pddl_files(pddl_output_dir: Path, domain_pddl: str, problem_pddl: str, player_id: str) -> tuple[str, str]:
    """
    Save PDDL domain and problem strings to files for debugging purposes.

    Creates timestamped files in the specified directory, useful for inspecting generated PDDL
    when planning fails or for verification.

    Args:
        pddl_output_dir (Path): The directory where PDDL files should be saved.
        domain_pddl (str): The PDDL domain string to save.
        problem_pddl (str): The PDDL problem string to save.
        player_id (str): Identifier for the player/session, used in filenames.

    Returns:
        tuple[str, str]: Paths to the saved domain and problem files as strings.

    Raises:
        None: Exceptions during file writing are caught and logged as warnings.

    Examples:
        >>> from pathlib import Path
        >>> save_pddl_files(Path("output"), "(domain test)", "(problem test)", "player1")
        ('output/planning_player1_domain.pddl', 'output/planning_player1_problem.pddl')
    """
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
    """
    Solve a PDDL planning problem using the unified_planning library with Fast Downward.

    Parses the provided PDDL strings, invokes the Fast Downward planner, and extracts the plan
    as a list of action strings. Handles optional dependency availability gracefully.

    Args:
        domain_pddl (str): The PDDL domain string defining actions and predicates.
        problem_pddl (str): The PDDL problem string defining the initial state and goal.

    Returns:
        Optional[List[str]]: A list of plan steps (e.g., ['move player loc1 loc2', 'pickup player item loc2']),
            or None if no plan is found or an error occurs.

    Raises:
        None: Exceptions are caught and logged; returns None on failure.

    Examples:
        >>> domain = "(define (domain test) (:action move ...))"
        >>> problem = "(define (problem test) (:init (at player start)) (:goal (at player goal)))"
        >>> plan = solve_with_unified_planning(domain, problem)
        >>> plan
        ['move player start goal']
    """
    if not UNIFIED_PLANNING_AVAILABLE or OneshotPlanner is None or PDDLReader is None:
        logger.error("Unified Planning library is not available.")
        return None
    
    try:
        logger.debug("Parsing PDDL with unified_planning")
        
        # Parse PDDL strings
        reader = PDDLReader()
        #logger.debug(f"PDDL domain raw: {domain_pddl}")
        #logger.debug(f"PDDL problem raw: {problem_pddl}")
        problem = reader.parse_problem_string(domain_pddl, problem_pddl)
        
        logger.debug(f"Parsed problem with {len(problem.actions)} actions")
        
        # Solve with Fast Downward
        planner = OneshotPlanner(problem_kind=problem.kind, name="fast-downward")
        logger.debug("Calling Fast Downward via unified_planning")
        result = planner.solve(problem) # type: ignore[attr-defined]
        
        if result.plan:
            # Extract plan steps
            plan_steps = []
            for action in result.plan.actions:
                action_str = f"{action.action.name}"
                if action.actual_parameters:
                    params = " ".join(str(p) for p in action.actual_parameters)
                    action_str += f" {params}"
                plan_steps.append(action_str)
            
            logger.debug(f"Extracted {len(plan_steps)} plan steps")
            return plan_steps
        else:
            logger.warning("No plan found by Fast Downward")
            return None
                
    except ImportError as e:
        logger.error(f"unified_planning not available: {e}")
        return None
    except Exception as e:
        logger.error(f"Error using unified_planning: {e}")
        return None

def extract_domain_predicates(domain_pddl: str) -> Dict[str, List[str]]:
    """
    Extracts predicate definitions from a PDDL domain.
    Returns a dict mapping predicate_name -> list_of_argument_names (e.g. ['?a']).
    
    Args:
        domain_pddl (str): The full PDDL domain string.
        
    Returns:
        Dict[str, List[str]]: Mapping of predicate names to their argument variables.
    """
    predicates_map = {}
    
    # 1. Find the predicates block
    # Find start of predicates
    start_idx = domain_pddl.find("(:predicates")
    if start_idx == -1:
        return {}
        
    # Find the matching closing parenthesis for the block
    # Simple counter approach
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
    
    # 2. Parse individual predicates
    # Matches (name ?arg1 ...)
    matches = re.findall(r'\(([\w-]+)(.*?)\)', pred_block)
    
    for pred_name, args_str in matches:
        if pred_name == ":predicates": continue # Skip the block definition itself
        
        # Extract arguments (starting with ?)
        args = re.findall(r'\?[\w-]+', args_str)
        predicates_map[pred_name] = args
        
    return predicates_map
