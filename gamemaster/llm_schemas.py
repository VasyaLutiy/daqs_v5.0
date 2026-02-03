from pydantic import BaseModel, Field
from typing import Optional, List

class StrategicGoal(BaseModel):
    """
    Determines the NPC's strategic goal based on conversation flow.
    """
    context_id: str = Field(..., description="The ID of the target context (e.g., 'ctx_identity', 'ctx_quest_offer') or the current context ID if no change is needed.")

class SocialIntent(BaseModel):
    """
    The NPC's social decision structured for PDDL execution.
    """
    pddl_action: str = Field(..., description="The PDDL action name (e.g., 'talk-normal', 'offer-quest'). Returns 'None' if no action fits.")
    reasoning: str = Field(..., description="Brief reasoning for choosing this action.")

class SemanticMatch(BaseModel):
    """
    Matching user input to world hypotheses.
    """
    matched_id: str = Field(..., description="The ID of the hypothesis that matches the user input, or 'None'.")
    reasoning: str = Field(..., description="Explanation of why this match was made or why no match was found.")

class QuestContent(BaseModel):
    """
    Narrative content for quest introductions or mission briefings.
    """
    internal_monologue: str = Field(..., description="The NPC's private thoughts, biases, and observations about the player/situation. NOT spoken aloud.")
    scene_description: str = Field(..., description="Atmospheric description of the scene and NPC behavior.")
    dialogue: str = Field(..., description="The NPC's spoken words, formatted with HTML breaks (<br>) for pacing.")

class SocialNarrative(BaseModel):
    """
    The generated story response and dialogue.
    """
    internal_monologue: str = Field(..., description="The NPC's private thoughts about the input. Use this to color the dialogue (e.g., 'He looks weak, I should mock him' -> Dialogue: 'Lost your nanny?').")
    scene_description: str = Field(..., description="Narrative description of the action's outcome and environment.")
    dialogue: str = Field(..., description="The NPC's verbal response to the player.")
