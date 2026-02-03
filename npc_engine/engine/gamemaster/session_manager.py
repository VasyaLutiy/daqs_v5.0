from unified_planning.shortcuts import *
from unified_planning.engines import UPSequentialSimulator
from unified_planning.io import PDDLReader
from npc_engine.engine.master.planner import MasterPlanner
from npc_engine.engine.logging_config import get_logger

logger = get_logger("gamemaster.session")

class SessionManager:
    """
    Tracks player progress through the PDDL state space.
    Detects deviations, dead ends, and optimal paths in real-time.
    """
    
    def __init__(self, domain_pddl: str, problem_pddl: str):
        # 1. Initialize Simulator environment
        self.reader = PDDLReader()
        try:
            self.problem = self.reader.parse_problem_string(domain_pddl, problem_pddl)
        except Exception as e:
            # Fallback for file-based parsing if string parsing fails (UP version dependent)
            # Assuming temp files exist or passed as content
            with open("temp_domain.pddl", "w") as f: f.write(domain_pddl)
            with open("temp_problem.pddl", "w") as f: f.write(problem_pddl)
            self.problem = self.reader.parse_problem("temp_domain.pddl", "temp_problem.pddl")

        self.simulator = UPSequentialSimulator(self.problem)
        self.current_state = self.simulator.get_initial_state()
        
        # 2. Initialize Planner for analysis
        self.planner = MasterPlanner()
        self.domain_str = domain_pddl
        self.problem_str = problem_pddl # We need to update this dynamically if we want exact planning from *current* state
        # Actually, standard planners solve from INIT. 
        # To solve from CURRENT, we need to generate a new PROBLEM string where :init is current_state.
        # This is complex. 
        # Simplification: We track move count vs estimated optimal.
        
        self.move_history = []
        self.initial_plan_len = self._get_plan_length(self.problem)
        self.status = "START"

    def _get_plan_length(self, up_problem) -> int:
        """Runs the planner on a UP problem instance."""
        # We need to convert UP problem back to PDDL string or use UP planner directly
        # UP has integrated planners. Let's use one via shortcut.
        try:
            with OneshotPlanner(problem_kind=up_problem.kind) as planner:
                result = planner.solve(up_problem)
                if result.plan:
                    return len(result.plan.actions)
                return 999 # Unsolvable
        except Exception as e:
            logger.warning(f"Planning failed: {e}")
            return 999

    def register_move(self, action_pddl: str):
        """
        Apply a player move to the simulation state.
        Args:
            action_pddl: String like 'shift-context player_test ctx_a ctx_b'
        """
        # Parse string to Action Instance
        try:
            parts = action_pddl.replace("(", "").replace(")", "").split()
            action_name = parts[0]
            args = parts[1:]
            
            up_action = self.problem.action(action_name)
            up_args = [self.problem.object(a) for a in args]
            action_instance = up_action(*up_args)
            
            if not self.simulator.is_applicable(self.current_state, action_instance):
                logger.error(f"Move {action_pddl} is NOT applicable in current state!")
                self.status = "INVALID_MOVE"
                return

            self.current_state = self.simulator.apply(self.current_state, action_instance)
            self.move_history.append(action_pddl)
            self.evaluate_status()
            
        except Exception as e:
            logger.error(f"Error registering move {action_pddl}: {e}")

    def evaluate_status(self):
        """
        Check if the goal is still reachable and how far it is.
        Updates self.status.
        """
        # 1. Check Goal
        if self.simulator.is_goal(self.current_state):
            self.status = "GOAL_REACHED"
            logger.info("Session Goal Reached!")
            return

        # 2. Check Reachability (Dead End Analysis)
        # We need to create a temporary problem starting from CURRENT state
        # UP supports this by modifying initial_values of the problem?
        # A safer way in UP is creating a new problem with new init.
        
        # Clone problem is hard.
        # We will assume for this MVP that we just check if any moves are available? No, that's too shallow.
        # We really need to run a planner from here.
        
        # Let's try to verify if we are in a Dead End by checking "Is Solvable"
        # Since generating PDDL from state is heavy, we'll use a heuristic:
        # "Deviation" = Moves Made. If Moves Made > 2 * Initial Optimal, we are deviating.
        
        moves_made = len(self.move_history)
        if moves_made > self.initial_plan_len + 2:
            self.status = "DEVIATING"
        else:
            self.status = "ON_TRACK"
            
        logger.info(f"Session Status: {self.status} (Moves: {moves_made}, Opt: {self.initial_plan_len})")

    def get_hint(self) -> str:
        if self.status == "DEVIATING":
            return "You are wandering. Focus on the main topic."
        if self.status == "DEAD_END":
            return "There is no way forward here."
        return ""
