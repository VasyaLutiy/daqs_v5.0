"""Master planner using PDDL solver."""

from typing import List, Optional, Tuple
from pathlib import Path
from . import logger
from .planner_libs import (
    diagnose_planning_failure,
    parse_actions_from_domain,
    parse_predicates,
    extract_predicates_from_goal,
    check_preconditions,
    save_pddl_files,
    solve_with_unified_planning
)
from ..logging_config import get_component_level
from ..world.player_state import PlayerState

class MasterPlanner:
    """Unified planner for quest generation."""

    def __init__(self, planner_path: Optional[str] = None, pddl_output_dir: str = "generated/pddl"):
        """Initialize the planner.

        Args:
            planner_path: Path to PDDL planner executable (not used with unified_planning)
            pddl_output_dir: Directory to save PDDL files for debugging
        """
        self.pddl_output_dir = Path(pddl_output_dir)
        self.pddl_output_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("MasterPlanner initialized with unified_planning")
        logger.debug(f"PDDL output directory: {pddl_output_dir}")
    
    def solve(self, domain_pddl: str, problem_pddl: str, player_id: str = "unknown", player_state: Optional[PlayerState] = None) -> Tuple[Optional[List[str]], Optional[str]]:
        """Solve the PDDL problem using unified_planning.

        Args:
            domain_pddl: PDDL domain string
            problem_pddl: PDDL problem string
            player_id: Player identifier for file naming
            player_state: PlayerState object for diagnostics

        Returns:
            Tuple of (List of plan steps, diagnostic message), or (None, diagnostic message) if no plan found
        """
        logger.debug("Starting PDDL planning with unified_planning")
        logger.debug(f"Domain length: {len(domain_pddl)} characters")
        logger.debug(f"Problem length: {len(problem_pddl)} characters")
        
        # Save PDDL files for debugging only when world component is at DEBUG level
        domain_file, problem_file = None, None
        world_level = get_component_level('world')
        logger.debug(f"World component logging level: {world_level}")
        if world_level == 'DEBUG':
            domain_file, problem_file = save_pddl_files(self.pddl_output_dir, domain_pddl, problem_pddl, player_id)
        
        # Use unified_planning to solve
        plan = solve_with_unified_planning(domain_pddl, problem_pddl)
        
        if plan is not None:
            logger.info(f"Planning completed successfully with {len(plan)} steps")
            logger.info(f"Plan steps: {plan}")
            return plan, None
        else:
            logger.warning("Planning failed - no plan found")
            
            # --- Advanced Diagnostics ---
            if player_state:
                diag_msg = diagnose_planning_failure(domain_pddl, problem_pddl, player_state)
                logger.warning(f"⚠️  Planning Alert: {diag_msg}")
            else:
                diag_msg = "No plan found – player state not available for diagnosis."
            
            return None, diag_msg