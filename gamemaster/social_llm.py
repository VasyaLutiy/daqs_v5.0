import os
import json
import re
from typing import Dict, Any, Optional, Union
from google import genai
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from gamemaster.prompt_orchestrator import orchestrator
from npc_engine.engine.logging_config import get_logger
from gamemaster.llm_schemas import (
    StrategicGoal, SocialIntent, SemanticMatch, 
    QuestContent, SocialNarrative
)

logger = get_logger("gamemaster.llm")

# Configuration
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower() # 'gemini' or 'grok'
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
GROK_MODEL = os.environ.get("GROK_MODEL", "grok-2-latest")

def format_dialogue(text: str) -> str:
    """Add line breaks to dialogue for better readability."""
    if not text: return ""
    # Add <br> after ellipses
    text = re.sub(r'(\.\.\.)\s*', r'\1<br>', text)
    # Add <br> after sentence endings
    text = re.sub(r'([.!?])\s+', r'\1<br>', text)
    # Add <br> after brackets like [action]
    text = re.sub(r'(\])\s*', r'\1<br>', text)
    # Add <br> after asterisks like *emphasis*
    text = re.sub(r'(\*)\s*([A-Z])', r'\1<br>\2', text)
    return text

def setup_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    return genai.Client(api_key=api_key)

def setup_grok_client():
    api_key = os.environ.get("GROK_API_KEY")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1",
    )

def get_strategic_goal(user_input: str, current_context: str) -> str:
    """
    Determines the NPC's strategic goal based on player input.
    """
    ctx_map = orchestrator.get_context_map()
    
    prompt = f"""
    You are the Strategic Mind of an NPC.
    Your task is to choose the best GOAL Context based on the conversation flow.
    
    Available Contexts:
    {ctx_map}
    
    Current Context: {current_context}
    Player said: "{user_input}"
    
    Rules:
    1. Analyze the player's intent. Do they want to change the topic?
    2. If the player expresses interest in a topic that matches one of the Available Contexts, output that Context ID.
    3. If the player wants to stay or continue the current topic, output the Current Context ID.
    4. If the input is ambiguous, default to Current Context.
    """

    try:
        if LLM_PROVIDER == "grok":
            client = setup_grok_client()
            completion = client.beta.chat.completions.parse(
                model=GROK_MODEL,
                messages=[
                    {"role": "system", "content": "You are the strategic engine of an NPC."},
                    {"role": "user", "content": prompt}
                ],
                response_format=StrategicGoal,
            )
            result = completion.choices[0].message.parsed
            goal = result.context_id
        else:
            # GEMINI FALLBACK
            client = setup_gemini_client()
            prompt += "\n5. Output ONLY the Context ID (e.g., 'ctx_identity'). No explanation."
            response = client.models.generate_content(
                model=GEMINI_MODEL, 
                contents=prompt
            )
            goal = response.text.strip().replace('`', '').strip()
            
        if "ctx_" in goal:
            return goal
        return current_context

    except Exception as e:
        logger.error(f"Strategy LLM Error ({LLM_PROVIDER}): {e}")
        return current_context

def get_social_intent(user_input: str, state: Dict[str, Any], available_moves: list) -> Optional[str]:
    """
    Analyzes user chat to determine the PDDL social action using Structured JSON.
    """
    prompt = orchestrator.assemble_nlu("social_intent", state, available_moves, user_input)
    logger.debug(f"--- NLU PROMPT START ---\n{prompt}\n--- NLU PROMPT END ---")

    try:
        if LLM_PROVIDER == "grok":
            client = setup_grok_client()
            completion = client.beta.chat.completions.parse(
                model=GROK_MODEL,
                messages=[
                    {"role": "system", "content": "You are an NLU engine converting natural language to PDDL actions."},
                    {"role": "user", "content": prompt}
                ],
                response_format=SocialIntent,
            )
            data = completion.choices[0].message.parsed
            action = data.pddl_action
            # reasoning = data.reasoning (logged if needed)
        else:
            # GEMINI
            client = setup_gemini_client()
            response = client.models.generate_content(
                model=GEMINI_MODEL, 
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            
            raw_text = response.text
            # Cleanup potential markdown wrapping
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
                
            json_data = json.loads(raw_text)
            
            # Handle case where Gemini returns a list instead of a dict
            if isinstance(json_data, list):
                if len(json_data) > 0:
                    json_data = json_data[0]
                else:
                    json_data = {} # fallback
                    
            action = json_data.get("pddl_action", "None")

        if action: action = action.strip()
        
        logger.info(f"[NLU Action] {action}")        
        
        if action == "None":
            return None
            
        if action not in available_moves:
            # Fuzzy match attempt
            # 1. Check if action is a simplified ID (e.g. "reveal-secret" vs "do_act_reveal_secrets...")
            simplified_key = action.replace("-", "_").lower()
            for move in available_moves:
                if simplified_key in move.lower():
                    logger.info(f"[NLU Recovery] Fuzzy matched '{action}' to '{move}'")
                    return move
            
            logger.warning(f"[NLU Warning] Hallucination detected: '{action}' is not in available_moves.")
            return None
            
        return action
    except Exception as e:
        logger.error(f"[Social LLM Error - {LLM_PROVIDER}] {e}")
        return None

def match_semantic_option(user_input: str, hypotheses: list) -> Dict[str, Any]:
    """
    Uses LLM to match user input to one of the pre-calculated world hypotheses.
    Returns a dict with 'matched_id' and 'reasoning'.
    """
    prompt = orchestrator.assemble_option_selection(user_input, hypotheses)
    logger.debug(f"--- SEMANTIC MATCH PROMPT ---\n{prompt}\n--- END PROMPT ---")
    
    try:
        if LLM_PROVIDER == "grok":
            client = setup_grok_client()
            completion = client.beta.chat.completions.parse(
                model=GROK_MODEL,
                messages=[
                    {"role": "system", "content": "You are a semantic matching engine."},
                    {"role": "user", "content": prompt}
                ],
                response_format=SemanticMatch,
            )
            result = completion.choices[0].message.parsed
            logger.info(f"[Semantic Match] Matched ID: {result.matched_id} | Reasoning: {result.reasoning}")
            return {"matched_id": result.matched_id, "reasoning": result.reasoning}
        else:
            # GEMINI
            client = setup_gemini_client()
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            raw_text = response.text
            # Cleanup markdown
            if raw_text.startswith("```json"): raw_text = raw_text[7:]
            if raw_text.endswith("```"): raw_text = raw_text[:-3]
            
            data = json.loads(raw_text)
            if isinstance(data, list): data = data[0] if data else {}
            
            logger.info(f"[Semantic Match] Matched ID: {data.get('matched_id')} | Reasoning: {data.get('reasoning')}")
            return data

    except Exception as e:
        logger.error(f"Semantic Matching Error ({LLM_PROVIDER}): {e}")
        return {"matched_id": "None", "reasoning": "Error in LLM processing."}

def generate_quest_intro(state: Dict[str, Any], quest_keys: list, target_ctx: str) -> Dict[str, str]:
    """
    Generates the Oracle-style Quest Prologue.
    """
    prompt = orchestrator.assemble_intro(state, quest_keys, target_ctx)
    logger.debug(f"--- QUEST INTRO PROMPT ---\n{prompt}\n--- END PROMPT ---")
    
    try:
        if LLM_PROVIDER == "grok":
            client = setup_grok_client()
            completion = client.beta.chat.completions.parse(
                model=GROK_MODEL,
                messages=[
                    {"role": "system", "content": "You are a fantasy narrator."},
                    {"role": "user", "content": prompt}
                ],
                response_format=QuestContent,
            )
            result = completion.choices[0].message.parsed
            dialogue = format_dialogue(result.dialogue)
            return {
                "internal_monologue": result.internal_monologue,
                "scene_description": result.scene_description, 
                "dialogue": dialogue
            }
        else:
            # GEMINI
            client = setup_gemini_client()
            # Add JSON instructions if missing from template
            prompt += "\n\nOUTPUT FORMAT:\nReturn a JSON object with 'internal_monologue', 'scene_description' and 'dialogue'. Escape quotes."
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            raw_text = response.text
            if raw_text.startswith("```json"): raw_text = raw_text[7:]
            if raw_text.endswith("```"): raw_text = raw_text[:-3]
            
            result = json.loads(raw_text)
            if isinstance(result, list): result = result[0] if result else {}
            
            result["dialogue"] = format_dialogue(result.get("dialogue", ""))
            return result

    except Exception as e:
        logger.error(f"Intro Generation Error ({LLM_PROVIDER}): {e}")
        return {"scene_description": "Error", "dialogue": "System reboot... (Intro Failed)"}

def generate_quest_mission(state: Dict[str, Any], pddl_plan: list, quest_name: str) -> Dict[str, str]:
    """
    Generates the mission briefing narrative based on a PDDL plan.
    """
    logger.debug(f"PDDL PLAN for Quest Mission: {pddl_plan}")
    prompt = orchestrator.assemble_quest_giver(state, pddl_plan, quest_name)
    logger.debug(f"--- QUEST MISSION PROMPT ---\n{prompt}\n--- END PROMPT ---")
    
    try:
        if LLM_PROVIDER == "grok":
            client = setup_grok_client()
            completion = client.beta.chat.completions.parse(
                model=GROK_MODEL,
                messages=[
                    {"role": "system", "content": "You are a quest giver."},
                    {"role": "user", "content": prompt}
                ],
                response_format=QuestContent,
            )
            result = completion.choices[0].message.parsed
            dialogue = format_dialogue(result.dialogue)
            return {
                "internal_monologue": result.internal_monologue,
                "scene_description": result.scene_description, 
                "dialogue": dialogue
            }
        else:
            # GEMINI
            client = setup_gemini_client()
            prompt += "\n\nOUTPUT FORMAT:\nReturn a JSON object with 'internal_monologue', 'scene_description' and 'dialogue'. Escape quotes."
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            raw_text = response.text
            if raw_text.startswith("```json"): raw_text = raw_text[7:]
            if raw_text.endswith("```"): raw_text = raw_text[:-3]
            
            result = json.loads(raw_text)
            if isinstance(result, list): result = result[0] if result else {}
            
            result["dialogue"] = format_dialogue(result.get("dialogue", ""))
            return result

    except Exception as e:
        logger.error(f"Mission Generation Error ({LLM_PROVIDER}): {e}")
        return {"scene_description": "Error", "dialogue": "System error... (Mission Briefing Failed)"}

def generate_social_narrative(action_str: str, state: Dict[str, Any], player_input: str = "") -> Dict[str, str]:
    """
    Generates the story response using the Prompt Orchestrator in JSON format.
    """
    # Assemble dynamic prompt
    prompt = orchestrator.assemble(action_str, state)
    
    # Inject player input
    prompt += f"\nPlayer Input: \"{player_input}\"\nRespond to this input within the action."
    
    logger.debug(f"--- GENERATED PROMPT START ---\n{prompt}\n--- GENERATED PROMPT END ---")
    
    try:
        # Resolve visual behavior if action is do_act_
        visual_prefix = ""
        if action_str.startswith("do_act_"):
            visual_prefix = orchestrator.translate_plan_to_narrative([action_str], state.get('active_persona', ''))
            if visual_prefix:
                visual_prefix = visual_prefix.strip() + " "

        if LLM_PROVIDER == "grok":
            client = setup_grok_client()
            completion = client.beta.chat.completions.parse(
                model=GROK_MODEL,
                messages=[
                    {"role": "system", "content": "You are a roleplay engine."},
                    {"role": "user", "content": prompt}
                ],
                response_format=SocialNarrative,
            )            
            result = completion.choices[0].message.parsed
            dialogue = format_dialogue(result.dialogue)
            return {
                "internal_monologue": result.internal_monologue,
                "scene_description": visual_prefix + result.scene_description, 
                "dialogue": dialogue
            }
        else:
            # GEMINI
            client = setup_gemini_client()
            prompt += "\n\nOUTPUT FORMAT:\nReturn a JSON object with 'internal_monologue', 'scene_description' and 'dialogue'. Escape quotes."
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            raw_text = response.text
            if raw_text.startswith("```json"): raw_text = raw_text[7:]
            if raw_text.endswith("```"): raw_text = raw_text[:-3]
            
            result = json.loads(raw_text)
            if isinstance(result, list): result = result[0] if result else {}
            
            result["dialogue"] = format_dialogue(result.get("dialogue", ""))
            if visual_prefix:
                result["scene_description"] = visual_prefix + result.get("scene_description", "")
            return result

    except Exception as e:
        logger.error(f"LLM Generation Error ({LLM_PROVIDER}): {e}")
        return {
            "scene_description": "System Error: Neural interface corrupted.",
            "dialogue": "I... cannot process... (JSON Parsing Failed)"
        }