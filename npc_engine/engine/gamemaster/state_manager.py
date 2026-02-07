"""
State Manager for DAQS Game Engine

Handles application of game actions and state transitions.
Manages the core game state updates for all player and NPC actions.
"""

from npc_engine.engine.logging_config import get_logger
from typing import Dict, Any

logger = get_logger("gamemaster.state")


class StateManager:
    """
    Manages game state updates and action application.

    Applies PDDL-formatted actions to the game state, handling
    context shifts, concept learning, trigger activation, and
    other state changes. Ensures state consistency and logs
    all modifications.
    """

    def __init__(self, cache: Dict[str, Dict] = None):
        """
        Initialize State Manager.
        Args:
            cache (Dict[str, Dict]): Optional configuration cache for logic lookups.
        """
        self.cache = cache or {"contexts": {}, "personas": {}, "triggers": {}, "world_map": {}}

    def apply_action(self, action_str: str, state: Dict[str, Any]):
        """
        Apply a PDDL-formatted action to the game state.
        """
        parts = action_str.split()
        if not parts:
            return

        act = parts[0]
        args = parts[1:]

        logger.info(f"StateManager: Executing action '{action_str}'")

        # Route to appropriate handler
        if act == "shift-context":
            self._apply_shift_context(args, state)
        elif act == "learn-concept":
            self._apply_learn_concept(args, state)
        elif act == "activate-trigger":
            self._apply_activate_trigger(args, state)
        elif act == "npc-offer":
            self._apply_npc_offer(args, state)
        elif act == "npc-flirt":
            self._apply_npc_flirt(args, state)
        elif act == "apply-concept":
            self._apply_concept(args, state)
        elif act == "apply-combo-concept":
            self._apply_combo_concept(args, state)
        elif act.startswith("do_"):
            # V2 Dynamic Actions
            self._apply_v2_action(act, args, state)
        elif act.startswith("deploy-"):
            self._apply_deploy_action(act, args, state)
        else:
            logger.warning(f"StateManager: Unknown action type '{act}'")

    def _apply_v2_action(self, action_id: str, args: list, state: Dict[str, Any]):
        """Applies V2 behavior action effects (if any)."""
        logger.info(f"StateManager: V2 Dynamic action applied: {action_id}")
        # Note: Narrative generation happens in the UI layer using PromptOrchestrator

    def _apply_shift_context(self, args: list, state: Dict[str, Any]):
        """Apply context shift and update mood if induced by context."""
        if len(args) < 3: return
        agent, old_ctx, new_ctx = args[:3]

        state["current_context"] = new_ctx
        if new_ctx not in state["visited_contexts"]:
            state["visited_contexts"].append(new_ctx)

        # MOOD INDUCTION LOGIC
        ctx_data = self.cache.get("contexts", {}).get(new_ctx, {})
        if ctx_data:
            new_mood = ctx_data.get("properties", {}).get("induces_mood")
            if new_mood:
                state["current_mood"] = new_mood
                logger.info(f"StateManager: Mood changed to {new_mood} by context {new_ctx}")

        logger.info(f"StateManager: Context shifted to {new_ctx}")

    def _apply_learn_concept(self, args: list, state: Dict[str, Any]):
        if len(args) < 3: return
        agent, ctx, concept = args[:3]
        if concept not in state["concepts"]:
            state["concepts"].append(concept)
            if "known_facts" in state:
                state["known_facts"].append(concept)
            logger.info(f"StateManager: Learned concept '{concept}'")

    def _apply_activate_trigger(self, args: list, state: Dict[str, Any]):
        if len(args) < 4: return
        agent, ctx, trigger, concept = args[:4]
        if trigger not in state.get("exhausted_triggers", []):
            if "exhausted_triggers" not in state: state["exhausted_triggers"] = []
            state["exhausted_triggers"].append(trigger)

        # Optional: mark shared items from trigger properties (e.g., presenting an item)
        trig_data = self.cache.get("triggers", {}).get(trigger, {})
        trig_props = trig_data.get("properties", {}) if isinstance(trig_data, dict) else {}
        provides_shared = trig_props.get("provides_shared_items", [])
        if provides_shared:
            shared = state.setdefault("shared_items", [])
            for item_id in provides_shared:
                if item_id not in shared:
                    shared.append(item_id)

        if concept not in state["concepts"]:
            state["concepts"].append(concept)
            if "known_facts" in state: state["known_facts"].append(concept)
            logger.info(f"StateManager: Trigger '{trigger}' yielded '{concept}'")

    def _apply_npc_offer(self, args: list, state: Dict[str, Any]):
        if len(args) < 4: return
        agent, ctx, trigger, concept = args[:4]
        if concept not in state["concepts"]:
            state["concepts"].append(concept)
            if "known_facts" in state: state["known_facts"].append(concept)
            logger.info(f"StateManager: NPC Offer '{trigger}' provided '{concept}'")

    def _apply_npc_flirt(self, args: list, state: Dict[str, Any]):
        if len(args) < 4: return
        agent, ctx, trigger, concept = args[:4]
        if concept not in state["concepts"]:
            state["concepts"].append(concept)
            if "known_facts" in state: state["known_facts"].append(concept)
            logger.info(f"StateManager: NPC Flirt '{trigger}' provided '{concept}'")

    def _apply_concept(self, args: list, state: Dict[str, Any]):
        if len(args) < 4: return
        agent, ctx, target, concept = args[:4]
        if target not in state.get("unlocked_contexts", []):
            if "unlocked_contexts" not in state: state["unlocked_contexts"] = []
            state["unlocked_contexts"].append(target)
        state["current_context"] = target
        if target not in state["visited_contexts"]:
            state["visited_contexts"].append(target)
        
        # Update mood if target context induces it
        ctx_data = self.cache.get("contexts", {}).get(target, {})
        if ctx_data:
            new_mood = ctx_data.get("properties", {}).get("induces_mood")
            if new_mood: state["current_mood"] = new_mood

        logger.info(f"StateManager: Auto-Shifted to {target}")

    def _apply_combo_concept(self, args: list, state: Dict[str, Any]):
        """Unlock/shift using two required concepts."""
        if len(args) < 5: 
            return
        agent, ctx, target, c1, c2 = args[:5]
        owned = set(state.get("concepts", []))
        if c1 not in owned or c2 not in owned:
            logger.warning(f"StateManager: Missing combo concepts for {target}: {c1}, {c2}")
            return
        if target not in state.get("unlocked_contexts", []):
            if "unlocked_contexts" not in state: state["unlocked_contexts"] = []
            state["unlocked_contexts"].append(target)
        state["current_context"] = target
        if target not in state["visited_contexts"]:
            state["visited_contexts"].append(target)

        ctx_data = self.cache.get("contexts", {}).get(target, {})
        if ctx_data:
            new_mood = ctx_data.get("properties", {}).get("induces_mood")
            if new_mood: state["current_mood"] = new_mood

        logger.info(f"StateManager: Combo unlock and shift to {target}")

    def _apply_deploy_action(self, action_type: str, args: list, state: Dict[str, Any]):
        if len(args) < 3: return
        agent, ctx, target = args[:3]
        if target not in state.get("unlocked_contexts", []):
            if "unlocked_contexts" not in state: state["unlocked_contexts"] = []
            state["unlocked_contexts"].append(target)
        state["current_context"] = target
        if target not in state["visited_contexts"]:
            state["visited_contexts"].append(target)
        
        # Mood check
        ctx_data = self.cache.get("contexts", {}).get(target, {})
        if ctx_data:
            new_mood = ctx_data.get("properties", {}).get("induces_mood")
            if new_mood: state["current_mood"] = new_mood

        logger.info(f"StateManager: Auto-Shifted to {target}")

    def validate_state_consistency(self, state: Dict[str, Any]) -> bool:
        issues = []
        required_keys = ["current_context", "concepts", "visited_contexts", "unlocked_contexts"]
        for key in required_keys:
            if key not in state: issues.append(f"Missing required key: {key}")
        if issues:
            logger.warning(f"StateManager: State consistency issues: {issues}")
            return False
        return True

    def create_backup_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        import copy
        return copy.deepcopy(state)

    def restore_state(self, state: Dict[str, Any], backup: Dict[str, Any]):
        state.clear()
        state.update(backup)
        logger.info("StateManager: State restored from backup")
