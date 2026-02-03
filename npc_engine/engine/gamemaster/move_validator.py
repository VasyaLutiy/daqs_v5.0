"""
Move Validator for DAQS Game Engine

Validates and generates all possible valid moves for the current game state.
Handles context navigation, trigger activation, concept learning, and NPC interactions.
"""

from npc_engine.engine.logging_config import get_logger
from typing import Dict, Any, List, Optional

logger = get_logger("gamemaster.moves")


class MoveValidator:
    """
    Validates and generates valid moves for the current game state.

    Analyzes the current context, player concepts, and persona tags to
    determine all possible actions the player can take. Includes context
    shifts, trigger activations, concept learning, and NPC interactions.

    Move Categories:
        - Context shifts: Navigate between conversation states
        - Concept learning: Gain knowledge from current context
        - Trigger activation: Use available actions and responses
        - NPC offers/flirts: Handle proactive NPC behaviors
        - Complex unlocks: Multi-requirement context access
    """

    def __init__(self, cache: Dict[str, Dict]):
        """
        Initialize move validator with configuration cache.

        Args:
            cache (Dict[str, Dict]): Pre-loaded configuration cache
        """
        self.cache = cache

    def get_valid_moves(self, state: Dict[str, Any]) -> List[str]:
        """
        Generate all valid moves for the current game state.

        Comprehensive analysis of possible player actions based on
        current context, owned concepts, persona tags, and game rules.

        Args:
            state (Dict[str, Any]): Current game state including:
                - current_context: Active conversation context
                - concepts: Player's acquired concepts
                - unlocked_contexts: Accessible contexts
                - active_persona: Current NPC persona
                - player_data: Player inventory and goals

        Returns:
            List[str]: Valid move strings in PDDL format

        Move Generation Process:
            1. Load persona tags and context data
            2. Generate context shift moves
            3. Add concept learning opportunities
            4. Include trigger activations
            5. Add NPC-initiated actions
        """
        moves = []
        agent = "player"

        # Extract state information
        current_context = state.get("current_context", "ctx_intro")
        owned_concepts = state.get("concepts", [])
        unlocked_contexts = state.get("unlocked_contexts", [])

        # Load persona data
        persona_id = state.get("active_persona", "persona_cyber")
        p_data = self.cache["personas"].get(persona_id, {})
        p_tags = p_data.get("tags", [])

        # Get current context data
        context_data = self.cache["contexts"].get(current_context, {})
        if not context_data:
            logger.warning(f"MoveValidator: No data for context '{current_context}'")
            return []

        # Generate different types of moves
        moves.extend(self._generate_context_shifts(agent, current_context, context_data, unlocked_contexts, owned_concepts))
        moves.extend(self._generate_concept_learning(agent, current_context, context_data, owned_concepts))

        moves.extend(self._generate_trigger_activations(agent, current_context, owned_concepts, p_tags))
        moves.extend(self._generate_npc_actions(state, owned_concepts, p_tags))

        # New: V2 Dynamic Behavior Rules
        moves.extend(self._generate_v2_behavior_moves(state, persona_id))

        return moves

    def _generate_v2_behavior_moves(self, state: Dict[str, Any], persona_id: str) -> List[str]:
        """
        Generate moves based on V2 behavior rules (mood and equipment based).
        
        Args:
            state (Dict[str, Any]): Current state
            persona_id (str): ID of the active persona
            
        Returns:
            List[str]: List of valid behavior moves
        """
        moves = []
        p_data = self.cache["personas"].get(persona_id, {})
        
        if "behavior_rules" not in p_data:
            return []
            
        # Get current mood from state (default to neutral)
        current_mood = state.get("current_mood", "neutral")
        agent = "player_001" # Default agent for social actions in this engine

        for rule in p_data["behavior_rules"]:
            # Check mood requirement
            if rule.get("mood") != current_mood:
                continue

            # Build arguments
            args = [agent]
            
            # Check Equipment Requirements
            # We need to find an item ID that satisfies the tag
            req_tag = rule.get("requires_holding_tag") or rule.get("requires_wearing_tag")
            
            if req_tag:
                item_id = self._find_item_with_tag(p_data, req_tag)
                if item_id:
                    args.append(item_id)
                    # Also append the tag object? 
                    # The PDDL domain usually expects ?item ?tag parameters
                    # Action: :parameters (?a ?item ?tag)
                    # So we should append the tag too to match the PDDL signature
                    args.append(req_tag)
                else:
                    # Required item not found on persona -> Action invalid
                    continue
            
            moves.append(f"do_{rule['id']} {' '.join(args)}")
                
        return moves

    def _find_item_with_tag(self, persona_data: Dict, tag: str) -> Optional[str]:
        """Helper to find first item ID with specific tag in any persona equipment category."""
        equipment = persona_data.get("equipment", {})
        
        # Iterate through all categories (clothes, weapons, items, etc.)
        for category in equipment.values():
            if isinstance(category, list):
                for item in category:
                    if tag in item.get("pddl_tags", []):
                        return item["id"]
                
        return None

    def _generate_context_shifts(self, agent: str, current_context: str,
                                context_data: Dict[str, Any], unlocked_contexts: List[str], owned_concepts: List[str]) -> List[str]:
        """
        Generate valid context shift moves.

        Args:
            agent (str): Action agent (usually "player")
            current_context (str): Current context ID
            context_data (Dict[str, Any]): Current context configuration
            unlocked_contexts (List[str]): List of unlocked context IDs
            owned_concepts (List[str]): List of concepts owned by the player

        Returns:
            List[str]: Context shift move strings
        """
        moves = []

        for conn in context_data.get("connections", []):
            target = conn["to"]
            t_data = self.cache["contexts"].get(target, {})
            can_shift = True

            if t_data:
                props = t_data.get("properties", {})

                # Check if target is locked
                if props.get("is_locked") and target not in unlocked_contexts:
                    can_shift = False

                    # Check for key-based unlock
                    req = props.get("required_concept")
                    if req and req in owned_concepts:
                        moves.append(f"apply-concept {agent} {current_context} {target} {req}")
                        logger.debug(f"MoveValidator: Found key '{req}' for {target}")

                    # Check for combo-based unlock
                    combo = props.get("required_combo")
                    if combo and len(combo) == 2:
                        c1, c2 = combo
                        if c1 in owned_concepts and c2 in owned_concepts:
                            moves.append(f"apply-combo-concept {agent} {current_context} {target} {c1} {c2}")
                            logger.debug(f"MoveValidator: Found combo keys '{c1}+{c2}' for {target}")

                # Check complex unlock requirements
                unlocks = props.get("unlock_actions", [])
                for unlock in unlocks:
                    act_name = unlock.get("action")
                    reqs = unlock.get("requires", [])
                    if all(r in owned_concepts for r in reqs):
                        items_str = " ".join(reqs)
                        moves.append(f"{act_name} {agent} {current_context} {target} {items_str}")
                        logger.debug(f"MoveValidator: Found complex unlock '{act_name}' for {target}")

            # Add direct shift if possible
            if can_shift:
                moves.append(f"shift-context {agent} {current_context} {target}")

        return moves

    def _generate_concept_learning(self, agent: str, current_context: str,
                                  context_data: Dict[str, Any], owned_concepts: List[str]) -> List[str]:
        """
        Generate concept learning moves.

        Args:
            agent (str): Action agent
            current_context (str): Current context ID
            context_data (Dict[str, Any]): Current context configuration
            owned_concepts (List[str]): Player's owned concepts

        Returns:
            List[str]: Concept learning move strings
        """
        moves = []

        if context_data.get("properties", {}).get("provides_concept"):
            concept = context_data["properties"]["provides_concept"]
            if concept not in owned_concepts:
                moves.append(f"learn-concept {agent} {current_context} {concept}")

        return moves

    def _generate_trigger_activations(self, agent: str, current_context: str,
                                     owned_concepts: List[str], persona_tags: List[str]) -> List[str]:
        """
        Generate trigger activation moves.

        Args:
            agent (str): Action agent
            current_context (str): Current context ID
            owned_concepts (List[str]): Player's owned concepts
            persona_tags (List[str]): Active persona tags

        Returns:
            List[str]: Trigger activation move strings
        """
        moves = []

        for t_data in self.cache["triggers"].values():
            p_ctx = t_data.get("parent_context")

            # Allow if global (no parent) OR matches current context
            if p_ctx is None or p_ctx == current_context:
                # Check requirements
                req = t_data.get("requires")
                if req and req not in owned_concepts:
                    continue

                req_tag = t_data.get("required_tag")
                if req_tag and req_tag not in persona_tags:
                    continue

                # Check if yields not already owned
                yields = t_data.get("yields", "unknown_concept")
                if yields not in owned_concepts:
                    moves.append(f"activate-trigger {agent} {current_context} {t_data['id']} {yields}")

        return moves

    def _generate_npc_actions(self, state: Dict[str, Any], owned_concepts: List[str],
                             persona_tags: List[str]) -> List[str]:
        """
        Generate NPC-initiated action moves.

        Args:
            state (Dict[str, Any]): Current game state
            owned_concepts (List[str]): Player's owned concepts
            persona_tags (List[str]): Active persona tags

        Returns:
            List[str]: NPC action move strings
        """
        from .npc_behavior import NPCBehavior

        npc_behavior = NPCBehavior()
        offers = npc_behavior.get_offers(state, owned_concepts, persona_tags)
        flirts = npc_behavior.get_flirts(state, owned_concepts, persona_tags)
        return offers + flirts

    def validate_move(self, move_str: str, state: Dict[str, Any]) -> bool:
        """
        Validate if a specific move is allowed in current state.

        Args:
            move_str (str): Move string to validate
            state (Dict[str, Any]): Current game state

        Returns:
            bool: True if move is valid, False otherwise
        """
        valid_moves = self.get_valid_moves(state)
        return move_str in valid_moves

    def get_available_contexts(self, state: Dict[str, Any]) -> List[str]:
        """
        Get all contexts the player can currently access.

        Args:
            state (Dict[str, Any]): Current game state

        Returns:
            List[str]: List of accessible context IDs
        """
        moves = self.get_valid_moves(state)
        contexts = []

        for move in moves:
            if move.startswith("shift-context"):
                parts = move.split()
                if len(parts) >= 4:
                    contexts.append(parts[3])  # target context

        return list(set(contexts))  # Remove duplicates

    def get_available_triggers(self, state: Dict[str, Any]) -> List[str]:
        """
        Get all triggers the player can currently activate.

        Args:
            state (Dict[str, Any]): Current game state

        Returns:
            List[str]: List of available trigger IDs
        """
        moves = self.get_valid_moves(state)
        triggers = []

        for move in moves:
            if move.startswith("activate-trigger"):
                parts = move.split()
                if len(parts) >= 4:
                    triggers.append(parts[3])  # trigger ID

        return triggers

    def analyze_move_complexity(self, move_str: str) -> Dict[str, Any]:
        """
        Analyze the complexity and requirements of a move.

        Args:
            move_str (str): Move string to analyze

        Returns:
            Dict[str, Any]: Analysis results with complexity metrics
        """
        analysis = {
            "type": "unknown",
            "complexity": 1,
            "requirements": [],
            "unlocks": []
        }

        parts = move_str.split()
        if not parts:
            return analysis

        action_type = parts[0]
        analysis["type"] = action_type

        if action_type == "shift-context":
            analysis["complexity"] = 1
        elif action_type == "activate-trigger":
            analysis["complexity"] = 2
            if len(parts) >= 5:
                analysis["requirements"] = [parts[4]]  # yield concept
        elif action_type == "apply-concept":
            analysis["complexity"] = 3
            if len(parts) >= 5:
                analysis["requirements"] = [parts[4]]  # required concept
                analysis["unlocks"] = [parts[3]]  # target context
        elif action_type.startswith("deploy-"):
            analysis["complexity"] = 4
            analysis["unlocks"] = [parts[3]] if len(parts) >= 4 else []

        return analysis