import yaml
import logging
import re
from pathlib import Path
from typing import Dict, Any, Callable, List
from npc_engine.engine.logging_config import get_logger

# Logger setup
logger = get_logger("gamemaster")

# Constants for defaults
DEFAULT_PERSONA_ID = 'persona_cyber'
DEFAULT_CONTEXT_ID = 'ctx_intro'
DEFAULT_SYSTEM_STYLE = "standard"

class PromptOrchestrator:
    def __init__(self, prompts_dir: str = "gamemaster/prompts"):
        self.base_dir = Path(prompts_dir)
        self.concepts_dir = Path("npc_engine/config/social_world/nodes/concepts")
        self.contexts_dir = Path("npc_engine/config/social_world/nodes/contexts")
        self.personas_dir = Path("npc_engine/config/social_world/nodes/personas")
        self.triggers_dir = Path("npc_engine/config/social_world/nodes/triggers")
        self.regions_dir = Path("npc_engine/config/world/nodes/regions")
        self.templates = {"system": {}, "actions": {}, "personas": {}, "nlu": {}}
        self.concepts_data = {}
        self.contexts_data = {}
        self.personas_data = {}
        self.triggers_data = {}
        self.locations_data = {}
        self.reload()

    def reload(self):
        """Force reloads all data and templates from disk."""
        self._load_all()
        self._load_yaml_data(self.concepts_dir, self.concepts_data, self._extract_concept_data)
        self._load_yaml_data(self.contexts_dir, self.contexts_data, self._extract_context_data)
        self._load_yaml_data(self.personas_dir, self.personas_data, self._extract_persona_data)
        self._load_yaml_data(self.triggers_dir, self.triggers_data, self._extract_trigger_data)
        self._load_locations()
        logger.info("Orchestrator: Data reloaded from disk.")

    def _load_locations(self):
        """Load location data from world regions."""
        self.locations_data = {}
        if self.regions_dir.exists():
            count = 0
            for f in self.regions_dir.glob("*.yaml"):
                try:
                    data = yaml.safe_load(f.read_text())
                    if "locations" in data and isinstance(data["locations"], list):
                        for loc in data["locations"]:
                            if "id" in loc:
                                self.locations_data[loc["id"]] = {
                                    "name": loc.get("name", loc["id"]),
                                    "description": loc.get("description", "An unknown location.")
                                }
                                logger.debug(f"Orchestrator: Registered location ID '{loc['id']}'")
                                count += 1
                except Exception as e:
                    logger.error(f"Error loading locations from {f}: {e}")
            logger.info(f"Orchestrator: Loaded {count} locations. IDs: {list(self.locations_data.keys())}")

    def _load_all(self):
        self.templates = {"system": {}, "actions": {}, "personas": {}, "nlu": {}}
        for category in ["system", "actions", "personas", "nlu"]:
            dir_path = self.base_dir / category
            if dir_path.exists():
                count = 0
                for f in dir_path.glob("*.yaml"):
                    try:
                        raw_data = yaml.safe_load(f.read_text())
                        file_stem = f.stem 
                        if isinstance(raw_data, dict):
                            if 'text' in raw_data:
                                self.templates[category][file_stem] = raw_data['text']
                                count += 1
                            else:
                                for sub_id, sub_data in raw_data.items():
                                    if isinstance(sub_data, dict) and 'text' in sub_data:
                                        key = f"{file_stem}-{sub_id}" if sub_id != 'default' else file_stem
                                        self.templates[category][key] = sub_data['text']
                                        count += 1
                    except Exception as e: 
                        logger.error(f"Error loading template {f}: {e}")
                logger.debug(f"Loaded {count} templates in '{category}'")

    def _load_yaml_data(self, dir_path: Path, data_dict: Dict[str, Any], extract_func: Callable[[Dict[str, Any]], tuple]):
        """Generic method to load YAML data from a directory."""
        if not dir_path.exists():
            return
        count = 0
        for f in dir_path.rglob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text())
                key, value = extract_func(data)
                data_dict[key] = value
                count += 1
            except Exception as e:
                logger.error(f"Error loading {f}: {e}")
        logger.info(f"Orchestrator: Loaded {count} items from {dir_path.name}.")

    def _extract_concept_data(self, data: Dict[str, Any]) -> tuple:
        # Handle new atlas format
        if data.get('type') == 'persona_group':
            # Extract concepts from atlas
            for concept in data.get('concepts', []):
                self.concepts_data[concept['id']] = {
                    'name': concept.get('name', concept['id']),
                    'content': concept.get('description', 'No details available.')
                }
            return data['id'], {}
        else:
            # Old format: single concept per file
            return data['id'], {'name': data.get('name', data['id']), 'content': data.get('content', 'No details available.')}

    def _extract_context_data(self, data: Dict[str, Any]) -> tuple:
        # Handle new atlas format
        if data.get('type') == 'persona_group':
            # Extract contexts from atlas
            for context in data.get('contexts', []):
                self.contexts_data[context['id']] = {
                    'name': context.get('name', context['id']),
                    'desc': context.get('description', 'No description.')
                }
            return data['id'], {}
        else:
            # Old format: single context per file
            return data['id'], {'name': data.get('name', data['id']), 'desc': data.get('description', 'No description.')}

    def _extract_persona_data(self, data: Dict[str, Any]) -> tuple:
        # Handle new atlas format
        if data.get('type') == 'persona_group':
            # Extract global concepts and triggers from atlas
            for concept in data.get('concepts', []):
                self.concepts_data[concept['id']] = {
                    'name': concept.get('name', concept['id']),
                    'content': concept.get('description', 'No details available.')
                }
            
            for trigger in data.get('triggers', []):
                self.triggers_data[trigger['id']] = trigger.get('name', trigger['id'])
            
            # Extract personas and their specific contexts
            for persona in data.get('personas', []):
                # Store the persona data
                self.personas_data[persona['id']] = persona
                
                # Extract persona-specific contexts
                for context in persona.get('contexts', []):
                    self.contexts_data[context['id']] = {
                        'name': context.get('name', context['id']),
                        'desc': context.get('description', 'No description.')
                    }
            
            # Return the atlas id and empty dict (atlas itself not used directly)
            return data['id'], {}
        else:
            # Old format: single persona per file
            return data['id'], data

    def _extract_trigger_data(self, data: Dict[str, Any]) -> tuple:
        # Handle new atlas format
        if data.get('type') == 'persona_group':
            # Extract triggers from atlas
            for trigger in data.get('triggers', []):
                self.triggers_data[trigger['id']] = trigger.get('name', trigger['id'])
            return data['id'], {}
        else:
            # Old format: single trigger per file
            return data['id'], data.get('name', data['id'])

    def _format_concepts(self, concept_ids: list) -> str:
        if not concept_ids: 
            return "None"
        lines = []
        for c_id in concept_ids:
            data = self.concepts_data.get(c_id, {'name': c_id, 'content': ''})
            lines.append(f"- {data['name']}: {data['content']}")
        return "\n" + "\n".join(lines)

    def _resolve_name(self, any_id: str) -> str:
        if any_id in self.concepts_data: 
            return self.concepts_data[any_id]['name']
        if any_id in self.triggers_data: 
            return self.triggers_data[any_id]
        if any_id in self.contexts_data: 
            return self.contexts_data[any_id]['name']
        return any_id

    def _get_available_triggers(self, ctx_id: str, persona_data: dict) -> Dict[str, str]:
        """Extract trigger descriptions for triggers available in the current context."""
        available_triggers = {}
        
        # Get triggers from persona data
        triggers = persona_data.get('triggers', [])
        
        for trigger in triggers:
            if trigger.get('parent_context') == ctx_id:
                trigger_name = trigger.get('name', trigger['id'])
                # Use the trigger name as both key and description for now
                # Could be enhanced to include more details
                available_triggers[trigger_name] = f"Available action: {trigger_name}"
        
        return available_triggers

    def _get_context_details(self, ctx_id: str, persona_data: dict) -> dict:
        """Get context details for the given context ID."""
        if ctx_id in self.contexts_data:
            return self.contexts_data[ctx_id]
        else:
            return {'name': ctx_id, 'desc': 'No description available.'}

    def get_context_map(self) -> str:
        # Note: This returns the BASE map. If we want persona-specific map, we'd need to pass persona_id.
        # For strategy, base map is usually fine, or we can update later.
        return "\n".join([f"- ID: {cid} | Name: {d['name']} | Desc: {d['desc']}" for cid, d in self.contexts_data.items()])

    def assemble_nlu(self, template_name: str, state: Dict[str, Any], valid_moves: list, user_input: str) -> str:
        # 1. Force template name to match our restored file if needed
        if template_name == "social_intent":
            template = self.templates["nlu"].get("social_intent") or self.templates["nlu"].get("social_intent-default")
        else:
            template = self.templates["nlu"].get(template_name, "")
        
        if not template:
            logger.error(f"NLU Template '{template_name}' not found! Falling back to raw moves.")
            return f"Choose move: {valid_moves} for input: {user_input}"

        # 2. Load persona
        persona_id = state.get('active_persona', DEFAULT_PERSONA_ID)
        p_data = self.personas_data.get(persona_id, {'name': 'Unknown', 'description': 'No data.'})
        
        # 3. Load Context Details
        ctx_id = state.get('current_topic', state.get('current_context', 'Unknown'))
        ctx_details = self._get_context_details(ctx_id, p_data)
        
        # 4. Extract available triggers
        available_triggers = self._get_available_triggers(ctx_id, p_data)
        trigger_info = "\n".join([f"- {name}: {desc}" for name, desc in available_triggers.items()]) if available_triggers else "No special triggers here."
        
        # 5. Format valid moves with DESCRIPTIONS (Crucial for Enterprise)
        formatted_moves = []
        for m in valid_moves:
            if m.startswith("do_act_"):
                parts = m.split()
                rule_id = parts[0][7:]
                description = "NPC Reaction"
                if "behavior_rules" in p_data:
                    for rule in p_data["behavior_rules"]:
                        if rule["id"] in [rule_id, "act_" + rule_id]:
                             description = rule.get("narrative_template", "").replace("{", "[").replace("}", "]")
                             break
                formatted_moves.append(f"- Reaction: {description} (System: {m})")
            
            elif m.startswith("shift-context"):
                parts = m.split()
                target_id = parts[3]
                target_ctx = self.contexts_data.get(target_id, {"name": target_id, "desc": "Navigate here."})
                formatted_moves.append(f"- Move to {target_ctx['name']}: {target_ctx['desc']} (System: {m})")
                
            elif m.startswith("apply-concept"):
                parts = m.split()
                target_id = parts[3]
                target_ctx = self.contexts_data.get(target_id, {"name": target_id, "desc": "Unlock this topic."})
                formatted_moves.append(f"- Start Conversation about {target_ctx['name']} (System: {m})")
            
            else:
                formatted_moves.append(f"- {m}")

        logger.info(f"Assembling NLU prompt: {template_name}")
        return template.format(
            context=f"{ctx_details['name']} ({ctx_details['desc']})",
            concepts=self._format_concepts(state.get('known_facts', [])),
            shared_items=", ".join(state.get("shared_items", [])) if state.get("shared_items") else "none",
            persona_name=p_data.get('name', 'Unknown'),
            persona_desc=p_data.get('description', 'No desc'),
            valid_moves="\n".join(formatted_moves),
            available_triggers=trigger_info,
            user_input=user_input
        )

    def assemble_option_selection(self, user_input: str, hypotheses: list) -> str:
        """Assembles a prompt for matching user input to a list of specific world objects."""
        template = self.templates["nlu"].get("option_selector", "")
        
        # Format the options list for the LLM
        options_str = "\n".join([f"- ID: {h['id']} | Name: {h['name']}" for h in hypotheses])
        
        return template.format(
            user_input=user_input,
            options=options_str
        )

    def _format_quest_keys(self, quest_keys: List[str]) -> str:
        """Formats quest keys into a readable string."""
        formatted_keys = []
        for k in quest_keys:
            if isinstance(k, str):
                resolved_name = self._resolve_name(k)
                formatted_keys.append(f"- {resolved_name}")
            else:
                formatted_keys.append(f"- {str(k)}")  # Fallback for non-string elements
        keys_str = "\n".join(formatted_keys)
        return keys_str if keys_str else "No specific concepts required at this time."

    def assemble_intro(self, state: Dict[str, Any], quest_keys: list, target_ctx: str) -> str:
        template = self.templates["system"].get("quest_intro", "")
        
        # 1. Load Persona
        persona_id = state.get('active_persona', DEFAULT_PERSONA_ID)
        p_data = self.personas_data.get(persona_id, {'name': 'Unknown', 'description': 'No data.'})
        
        # 2. Load Start Context
        ctx_id = state.get('current_context', DEFAULT_CONTEXT_ID)
        ctx_details = self._get_context_details(ctx_id, p_data)
        
        # 3. Load Target Context Name
        target_details = self._get_context_details(target_ctx, p_data)
        
        # 4. Format Keys
        keys_str = self._format_quest_keys(quest_keys)
        
        # 5. Load Location Data
        loc_id = state.get("current_location", "unknown")
        loc_data = self.locations_data.get(loc_id, {'name': 'Unknown Location', 'description': 'An unspecified place.'})
        
        # 6. Get Oracle Interpretation Style
        oracle_style = p_data.get("properties", {}).get("oracle_interpretation", "a strange flicker of intuition")
        
        return template.format(
            context_name=ctx_details['name'],
            context_desc=ctx_details['desc'],
            location_name=loc_data['name'],
            location_desc=loc_data['description'],
            target_name=target_details['name'],
            quest_keys=keys_str,
            persona_name=p_data.get('name', 'Unknown'),
            persona_desc=p_data.get('description', 'No desc'),
            oracle_style=oracle_style
        )

    def _format_pddl_plan(self, pddl_plan: List[str]) -> str:
        """Formats PDDL plan into readable steps."""
        readable_plan = []
        for step in pddl_plan:
            # Simple PDDL parser: (action arg1 arg2) -> Action: Name1 Name2
            clean_step = step.replace("(", "").replace(")", "")
            parts = clean_step.split()
            if not parts: 
                continue
            
            verb = parts[0].replace("-", " ").title()
            args = [self._resolve_name(a).replace("_", " ").title() for a in parts[1:]]
            readable_plan.append(f"- {verb}: {' '.join(args)}")
        
        return "\n".join(readable_plan) if readable_plan else "The logistics are already aligned."

    def assemble_quest_giver(self, state: Dict[str, Any], pddl_plan: list, quest_name: str) -> str:
        """Assembles the mission briefing prompt by resolving PDDL IDs to names."""
        template = self.templates["system"].get("quest_mission", "")
        
        # 1. Load Persona
        persona_id = state.get('active_persona', DEFAULT_PERSONA_ID)
        p_data = self.personas_data.get(persona_id, {'name': 'Unknown', 'description': 'No data.'})
        
        # 2. Format Plan
        plan_str = self._format_pddl_plan(pddl_plan)
        
        return template.format(
            persona_name=p_data.get('name', 'Unknown'),
            persona_desc=p_data.get('description', 'No desc'),
            quest_name=quest_name,
            pddl_plan=plan_str
        )

    def translate_plan_to_narrative(self, plan: List[str], persona_id: str) -> str:
        """Translates a PDDL plan into a narrative description using persona behavior rules."""
        if not plan:
            return ""

        # 1. Load Persona Data
        p_data = self.personas_data.get(persona_id, {})
        if not p_data:
            return ""

        # 2. Build Maps
        rules_map = {}
        if "behavior_rules" in p_data:
            for rule in p_data["behavior_rules"]:
                rules_map[rule["id"]] = rule.get("narrative_template", "")

        item_map = {}
        if "equipment" in p_data:
            for cat in p_data["equipment"].values():
                for item in cat:
                    item_map[item["id"]] = item.get("name", item["id"])

        # 3. Translate Steps
        narrative_parts = []
        for step in plan:
            # step: "do_act_staff_threat player_001 item_crystal_staff focus"
            clean_step = step.replace("(", "").replace(")", "")
            parts = clean_step.split()
            if not parts: continue
            
            action_name = parts[0]
            # Handle 'do_' prefix from V2 domain
            if action_name.startswith("do_"):
                rule_id = action_name[3:]
            else:
                rule_id = action_name

            if rule_id in rules_map:
                template = rules_map[rule_id]
                logger.info(f"VisualGen: Matched rule '{rule_id}' with template: '{template}'")
                
                # Resolving arguments (specifically item_name)
                # Heuristic: look for any arg that matches an item ID
                item_name = "something"
                for arg in parts[1:]:
                    if arg in item_map:
                        item_name = item_map[arg]
                        logger.debug(f"VisualGen: Resolved item '{arg}' to name '{item_name}'")
                        break
                
                # Format
                try:
                    desc = template.format(item_name=item_name)
                    logger.info(f"VisualGen: Generated description: '{desc}'")
                    narrative_parts.append(desc)
                except Exception as e:
                    logger.warning(f"VisualGen: Failed to format narrative for {rule_id}: {e}")
                    narrative_parts.append(template) # Fallback to raw template

        return " ".join(narrative_parts)

    def assemble(self, action_str: str, state: Dict[str, Any], system_style: str = DEFAULT_SYSTEM_STYLE) -> str:
        # 1. Load Persona
        persona_id = state.get('active_persona', DEFAULT_PERSONA_ID)
        p_data = self.personas_data.get(persona_id, {'name': 'Default NPC', 'description': 'A generic character.'})

        # 2. Load Context WITH Overrides
        ctx_id = state.get('current_topic', 'Unknown')
        ctx_details = self._get_context_details(ctx_id, p_data)

        # 3. System Part
        sys_template = self.templates["system"].get(system_style, "")
        system_part = sys_template.format(
            context_name=ctx_details['name'], 
            context_desc=ctx_details['desc'],
            current_mood=state.get('current_mood', 'neutral'),
            persona_name=p_data.get('name', 'Unknown'), 
            persona_desc=p_data.get('description', 'No desc'),
            concepts=self._format_concepts(state.get('known_facts', []))
        )

        # Add location details
        location_id = state.get('current_location', 'unknown')
        logger.info(f"Orchestrator: Assembling prompt for location '{location_id}'")
        
        loc_data = self.locations_data.get(location_id, {'name': 'Unknown Location', 'description': 'An unspecified place.'})
        if location_id == 'unknown' or location_id not in self.locations_data:
            logger.warning(f"Orchestrator: Location ID '{location_id}' not found in loaded data! Available: {list(self.locations_data.keys())}")
            
        system_part += f"\n\nCurrent Location: {loc_data['name']}\n{loc_data['description']}"

        # 4. Action Part
        clean_action = action_str.replace("Player: ", "").replace("AI: ", "")
        full_act_id = clean_action.split()[0]
        verb_prefix = full_act_id.split('-')[0]
        
        act_template = self.templates["actions"].get(full_act_id)
        if not act_template: 
            act_template = self.templates["actions"].get(verb_prefix)
        if not act_template: 
            act_template = self.templates["actions"].get("default", "")
        
        parts = clean_action.split()
        
        # Special handling for NPC offers
        if full_act_id == "npc-offer":
            # Extract parameters: npc-offer player ctx_tavern_intro trig_dolores_offers_partnership cpt_dolores_offer
            offered_concept = parts[-1] if len(parts) > 3 else "unknown_offer"
            trigger_name = parts[3] if len(parts) > 3 else "unknown_trigger"
            
            action_part = act_template.format(
                target=trigger_name,
                offered_concept=offered_concept,
                action_name=clean_action,
                context_name=ctx_details['name'],
                context_desc=ctx_details['desc'],
                persona_name=p_data.get('name', 'Unknown'),
                persona_desc=p_data.get('description', 'No desc'),
                concepts=self._format_concepts(state.get('known_facts', [])),
                rapport="neutral"  # Could be enhanced to track rapport levels
            )
        elif full_act_id == "npc-flirt":
            # Extract parameters: npc-flirt player ctx_tavern_intro trig_dolores_flirts cpt_dolores_flirt
            offered_concept = parts[-1] if len(parts) > 3 else "unknown_flirt"
            trigger_name = parts[3] if len(parts) > 3 else "unknown_trigger"
            
            action_part = act_template.format(
                target=trigger_name,
                offered_concept=offered_concept,
                action_name=clean_action,
                context_name=ctx_details['name'],
                context_desc=ctx_details['desc'],
                persona_name=p_data.get('name', 'Unknown'),
                persona_desc=p_data.get('description', 'No desc'),
                concepts=self._format_concepts(state.get('known_facts', [])),
                rapport="neutral"
            )
        else:
            readable_target = self._resolve_name(parts[-1]) if len(parts) > 1 else "Unknown"
            action_part = act_template.format(target=readable_target, action_name=clean_action)

        return f"{system_part}\n\n{action_part}\n\nSTORYTELLING START:"

orchestrator = PromptOrchestrator()
