"""
NPC Behavior Engine for DAQS

Handles NPC-initiated actions including offers, flirts, and other
proactive behaviors based on persona tags and player state.
"""

from npc_engine.engine.logging_config import get_logger
from typing import Dict, Any, List

logger = get_logger("gamemaster.npc")


class NPCBehavior:
    """
    Manages NPC-initiated behaviors and interactions.

    Generates appropriate NPC actions based on personality tags,
    player state, and current context. Supports offers, flirts,
    and other proactive NPC behaviors.

    Behavior Logic:
        - Proactive NPCs can initiate conversations and offers
        - Personality tags determine behavior types
        - Player state influences NPC decisions
        - Context restrictions apply to all actions
    """

    def get_offers(self, state: Dict[str, Any], owned_concepts: List[str], persona_tags: List[str]) -> List[str]:
        """
        Generate NPC-initiated partnership/companion offers.

        Based on persona tags and player capability assessment.
        Proactive mercenary NPCs will offer partnerships when
        player has active quests.

        Args:
            state (Dict[str, Any]): Current game state
            owned_concepts (List[str]): Player's acquired concepts
            persona_tags (List[str]): Active persona's behavior tags

        Returns:
            List[str]: List of offer action strings in PDDL format

        Offer Conditions:
            - Requires "proactive" and "mercenary" tags
            - Must be in tavern context
            - Player needs active quest (not null/empty)
            - Offer concept not already owned
        """
        offers = []
        current_context = state.get("current_context", "ctx_intro")
        persona_id = state.get("active_persona", "persona_cyber")

        # Proactive mercenary NPCs offer partnerships
        if ("proactive" in persona_tags and
            "mercenary" in persona_tags and
            current_context == "ctx_tavern_intro"):

            # Check if player has active quest
            player_goal = state.get("player_data", {}).get("goal")
            has_active_quest = player_goal and player_goal not in ["", "null", None]

            # Generate offer if conditions met
            if has_active_quest:
                offer_concept = f"cpt_{persona_id}_offer"
                if offer_concept not in owned_concepts:
                    offers.append(f"npc-offer player ctx_tavern_intro trig_{persona_id}_offers_partnership {offer_concept}")
                    logger.debug(f"NPC {persona_id}: Generated partnership offer")

        return offers

    def get_flirts(self, state: Dict[str, Any], owned_concepts: List[str], persona_tags: List[str]) -> List[str]:
        """
        Generate NPC-initiated flirtatious advances.

        Based on persona tags and player capability assessment.
        Proactive NPCs may flirt when player shows promise or wealth.

        Args:
            state (Dict[str, Any]): Current game state
            owned_concepts (List[str]): Player's acquired concepts
            persona_tags (List[str]): Active persona's behavior tags

        Returns:
            List[str]: List of flirt action strings in PDDL format

        Flirt Conditions:
            - Requires "proactive" tag
            - Must be in tavern context
            - Player shows capability (quest potential or gold)
            - Flirt concept not already owned
        """
        flirts = []
        current_context = state.get("current_context", "ctx_intro")
        persona_id = state.get("active_persona", "persona_cyber")

        # Proactive NPCs can flirt
        if "proactive" in persona_tags and current_context == "ctx_tavern_intro":
            # Check if player shows capability
            has_quest_potential = any(c in owned_concepts for c in ["cpt_quest_easy", "cpt_quest_hard"])
            has_gold = state.get("player_data", {}).get("inventory", {}).get("items", {}).get("gold", 0) > 0

            # Generate flirt if player seems capable
            if has_quest_potential or has_gold:
                flirt_concept = f"cpt_{persona_id}_flirt"
                if flirt_concept not in owned_concepts:
                    flirts.append(f"npc-flirt player ctx_tavern_intro trig_{persona_id}_flirts {flirt_concept}")
                    logger.debug(f"NPC {persona_id}: Generated flirt action")

        return flirts

    def get_initiatives(self, state: Dict[str, Any], owned_concepts: List[str], persona_tags: List[str]) -> List[str]:
        """
        Generate a single best NPC-initiated action (priority: offer > flirt).

        Args:
            state (Dict[str, Any]): Current game state
            owned_concepts (List[str]): Player's acquired concepts
            persona_tags (List[str]): Active persona's behavior tags

        Returns:
            List[str]: List containing at most one NPC-initiated action string
        """
        # Priority 1: Partnership/Quest Offers
        offers = self.get_offers(state, owned_concepts, persona_tags)
        if offers:
            return [offers[0]]

        # Priority 2: Flirtatious Advances
        flirts = self.get_flirts(state, owned_concepts, persona_tags)
        if flirts:
            return [flirts[0]]

        return []

    def should_initiate_conversation(self, state: Dict[str, Any], persona_tags: List[str]) -> bool:
        """
        Determine if NPC should initiate conversation.

        Some NPCs may start talking without player prompting,
        especially in appropriate contexts.

        Args:
            state (Dict[str, Any]): Current game state
            persona_tags (List[str]): Active persona's behavior tags

        Returns:
            bool: True if NPC should initiate conversation

        Initiation Conditions:
            - "proactive" tag present
            - In appropriate social context
            - Player not already engaged
        """
        if "proactive" not in persona_tags:
            return False

        current_context = state.get("current_context", "ctx_intro")
        social_contexts = ["ctx_tavern_intro", "ctx_party", "ctx_market"]

        return current_context in social_contexts

    def get_personality_modifiers(self, persona_tags: List[str]) -> Dict[str, float]:
        """
        Calculate personality-based behavior modifiers.

        Different personality tags affect how NPC responds to
        various situations and player actions.

        Args:
            persona_tags (List[str]): Active persona's behavior tags

        Returns:
            Dict[str, float]: Modifier values for different behaviors

        Modifier Keys:
            - friendliness: Base approachability (-1.0 to 1.0)
            - greed: Profit motivation (0.0 to 1.0)
            - caution: Risk aversion (0.0 to 1.0)
            - curiosity: Interest in player actions (0.0 to 1.0)
        """
        modifiers = {
            "friendliness": 0.0,
            "greed": 0.0,
            "caution": 0.5,
            "curiosity": 0.3
        }

        # Apply tag-based modifications
        if "mercenary" in persona_tags:
            modifiers["greed"] = 0.8
            modifiers["caution"] = 0.7

        if "helpful" in persona_tags:
            modifiers["friendliness"] = 0.6
            modifiers["curiosity"] = 0.5

        if "aggressive" in persona_tags:
            modifiers["friendliness"] = -0.4
            modifiers["caution"] = 0.2

        if "mysterious" in persona_tags:
            modifiers["curiosity"] = 0.1
            modifiers["caution"] = 0.8

        return modifiers