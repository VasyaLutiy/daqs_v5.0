from pathlib import Path

from gamemaster.prompt_orchestrator import orchestrator
from npc_engine.engine.gamemaster.cache_manager import CacheManager
from npc_engine.engine.gamemaster.state_manager import StateManager


CONFIG_DIR = Path("npc_engine/config")


def test_shared_item_carried_into_nlu_prompt():
    """
    Ensure a trigger that provides_shared_items updates state and flows into the NLU prompt.
    """
    cache = CacheManager(CONFIG_DIR).cache
    sm = StateManager(cache)

    state = {
        "current_context": "ctx_neutral_talk",
        "active_persona": "persona_dolores",
        "current_location": "tavern",
        "concepts": [],
        "visited_contexts": ["ctx_tavern_intro"],
        "unlocked_contexts": [],
        "exhausted_triggers": [],
        "known_facts": [],
    }

    action = "activate-trigger player ctx_neutral_talk trig_find_coin cpt_shadow_token"
    sm.apply_action(action, state)

    assert "item_shadow_coin" in state.get("shared_items", [])

    prompt = orchestrator.assemble_nlu(
        "social_intent",
        state,
        [action],
        user_input="test input",
    )

    assert "Shared Items (offered by player): item_shadow_coin" in prompt
