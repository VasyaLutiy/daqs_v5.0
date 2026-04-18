"""Dialogue subsystem: typed state, FSM engine, and domain compiler."""
from npc_engine.engine.dialogue.state import SocialState
from npc_engine.engine.dialogue.engine import DialogueEngine, DialogueMove

__all__ = ["SocialState", "DialogueEngine", "DialogueMove"]
