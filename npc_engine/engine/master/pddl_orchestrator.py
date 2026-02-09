import jinja2
from pathlib import Path
from typing import Dict, Any, Set, Tuple
from npc_engine.engine.world.graph import WorldGraph
from npc_engine.engine.world.player_state import PlayerState
from npc_engine.engine.logging_config import logging_manager, get_component_level
import yaml
from npc_engine.engine.master.pddl_libs import SocialWorldAssembler
from npc_engine.engine.master.pddl_builder import PDDLTemplateRenderer

logger = logging_manager.get_component_logger('master')

class PDDLOrchestrator:
    def __init__(self, logic_dir: str = "npc_engine/config/logic"):
        self.logic_dir = Path(logic_dir)
        # Add social world config to template search path for V2
        social_dir = Path("npc_engine/config/social_world")
        self.renderer = PDDLTemplateRenderer([self.logic_dir, social_dir])

    def _extract_constants(self, persona_data: Dict[str, Any]) -> Dict[str, Set[str]]:
        constants = {"tags": set(), "moods": set(), "actions": set()}
        if not persona_data:
            return constants
            
        # From Rules
        if "behavior_rules" in persona_data:
            for rule in persona_data["behavior_rules"]:
                if "id" in rule: constants["actions"].add(rule["id"])
                if "mood" in rule: constants["moods"].add(rule["mood"])
                if "requires_holding_tag" in rule and rule["requires_holding_tag"]:
                        constants["tags"].add(rule["requires_holding_tag"])
                if "requires_wearing_tag" in rule and rule["requires_wearing_tag"]:
                        constants["tags"].add(rule["requires_wearing_tag"])
        
        # From Equipment
        if "equipment" in persona_data:
            for cat in persona_data["equipment"].values():
                for item in cat:
                    if "pddl_tags" in item:
                        for tag in item["pddl_tags"]:
                            constants["tags"].add(tag)
                            
        return constants

    def get_domain(self, mode: str, persona_data: Dict[str, Any] = None, constants: Dict[str, Set[str]] = None) -> str:
        """
        Gets the PDDL domain. Supports V2 dynamic domains if persona has behavior rules.
        """
        # Check for dynamic behavior capability (V2 Architecture)
        use_dynamic_v2 = False
    
        if persona_data and "behavior_rules" in persona_data:
            use_dynamic_v2 = True

        if use_dynamic_v2 and mode == "social":
            template_path = "social/social_unified_v4.pddl.j2"
            try:
                logger.info(f"Using V4 Social Domain Template: {template_path}")
                # Pass constants to template
                return self.renderer.render(template_path, {"persona": persona_data, "constants": constants})
            except jinja2.TemplateNotFound:
                logger.error(f"V4 Template not found: {template_path}")
                # Fallback to older V2 if V4 missing
                try:
                    return self.renderer.render("social_domain_v2.pddl.j2", {"persona": persona_data, "constants": constants})
                except: return ""
        else:
            # Fallback to standard static domain
            domain_path = self.logic_dir / mode / "domain.pddl"
            try:
                return domain_path.read_text()
            except FileNotFoundError:
                logger.error(f"Domain file not found: {domain_path}")
                return ""

    def assemble_problem(self, mode: str, player_state: PlayerState, world_graph: WorldGraph, goal_pddl: str) -> str:
        # Build data similar to _generate_problem
        types = world_graph.get_all_pddl_types()
        
        # Objects
        objects = []
        for type_name, obj_list in types.items():
            if obj_list:
                objects.append(f"{' '.join(obj_list)} - {type_name}")
        objects.append(f"{player_state.player_id} - object")

        # Identify Locked Locations
        locked_locs = {}
        for loc_id, loc in world_graph.locations.items():
            if loc.properties.get("is_locked"):
                req = loc.properties.get("required_concept")
                if req:
                    locked_locs[loc_id] = req

        # Initial State
        init_facts = [
            f"(at {player_state.player_id} {player_state.current_location})",
            f"(controllable {player_state.player_id})"
        ]

        # Inventory
        for item_id in player_state.inventory.items.keys():
            init_facts.append(f"(has-item {player_state.player_id} {item_id})")

        # Item/Object/NPC Placement
        for loc_id, loc in world_graph.locations.items():
            for item_id in loc.contained_items:
                init_facts.append(f"(at {item_id} {loc_id})")
            for npc_id in loc.contained_npcs:
                init_facts.append(f"(at {npc_id} {loc_id})")
            for obj_id in loc.contained_objects:
                init_facts.append(f"(at {obj_id} {loc_id})")
                
                # Portal Logic
                obj_node = world_graph.get_node(obj_id)
                if obj_node and obj_node.properties.get("is_portal"):
                    target = obj_node.properties.get("target_location")
                    key = obj_node.properties.get("requires_item")
                    if target and key:
                        init_facts.append(f"(portal_link {obj_id} {target})")
                        init_facts.append(f"(portal_key {obj_id} {key})")

        # Topology and Path Blocking
        for edge in world_graph.edges:
            etype = str(edge.edge_type.value) if hasattr(edge.edge_type, 'value') else str(edge.edge_type)
            
            init_facts.append(f"(path {edge.from_node} {edge.to_node})")
            
            if etype == "portal":
                continue
            
            if edge.to_node in locked_locs:
                req_item = locked_locs[edge.to_node]
                init_facts.append(f"(blocked {edge.from_node} {edge.to_node} {req_item})")
            else:
                init_facts.append(f"(path_available {edge.from_node} {edge.to_node})")

        # Accessibility
        for loc_id in player_state.discovered_locations:
            if loc_id in world_graph.locations and loc_id not in locked_locs:
                init_facts.append(f"(accessible {loc_id})")
        init_facts.append(f"(accessible {player_state.current_location})")

        init_facts = sorted(list(set(init_facts)))

        data = {
            "world_id": world_graph.world_id,
            "domain_id": mode,
            "types": types,
            "player_id": player_state.player_id,
            "init_facts": init_facts,
            "goal_pddl": goal_pddl
        }
        
        return self.renderer.render(f"{mode}/problem.pddl.j2", data)

    def get_persona_metadata(self, persona_id: str, config_dir: str = "npc_engine/config/social_world") -> Dict[str, Any]:
        """
        Extracts start context and other properties for a specific persona.
        Useful for UI initialization.
        """
        config_path = Path(config_dir)
        contexts = {}
        personas = {}
        
        # 1. Load All Personas
        pers_dir = config_path / "nodes" / "personas"
        if pers_dir.exists():
            for f in pers_dir.rglob("*.yaml"):
                data = yaml.safe_load(f.read_text())
                if "personas" in data and isinstance(data["personas"], list):
                    for p in data["personas"]:
                        if "id" in p: personas[p['id']] = p
                elif "id" in data:
                    personas[data['id']] = data

        if persona_id not in personas:
            return {"start_context": "ctx_intro", "target_goal": "ctx_core", "properties": {}, "tags": []}

        p_data = personas[persona_id]
        
        # 2. Load Contexts from Persona Data (handles both old and new formats)
        contexts = {}
        
        # Check if persona has nested contexts (new atlas format)
        if "contexts" in p_data:
            for c in p_data["contexts"]:
                contexts[c['id']] = c
        else:
            # Old format: load from separate context files
            ctx_dir = config_path / "nodes" / "contexts"
            if ctx_dir.exists():
                for f in ctx_dir.rglob("*.yaml"):
                    data = yaml.safe_load(f.read_text())
                    if "contexts" in data: # Atlas
                        for c in data["contexts"]: contexts[c['id']] = c
                    else: # Single
                        contexts[data['id']] = data

        # 3. Apply Overrides
        overrides = p_data.get('world_overrides', {})
        for cid, props in overrides.items():
            if cid in contexts:
                for k, v in props.items():
                    if 'properties' not in contexts[cid]: contexts[cid]['properties'] = {}
                    contexts[cid]['properties'][k] = v

        # 4. Find Start Context
        start_ctx = next((cid for cid, c in contexts.items() if c.get('properties', {}).get('is_start')), "ctx_intro")
        
        # 5. Get Target Goal from Persona properties or default
        target_goal = p_data.get("properties", {}).get("target_social_goal", "ctx_core")

        return {
            "start_context": start_ctx,
            "target_goal": target_goal,
            "persona_name": p_data.get("name", persona_id),
            "contexts": contexts,
            "properties": p_data.get("properties", {}),
            "tags": p_data.get("tags", []),
            "has_v2_behavior": "behavior_rules" in p_data # Flag for UI to know this is a V2 persona
        }

    def generate(self, mode: str, player_state: PlayerState, world_graph: WorldGraph, goal_pddl: str, dynamic_state: Dict[str, Any] = None, active_persona: str = None) -> tuple[str, str]:
        logger.info(f"PDDLOrchestrator.generate called for mode {mode} with goal {goal_pddl}")
        
        # Need to fetch persona data early to determine if we use V2 logic
        persona_data = {}
        if active_persona:
             config_path = Path("npc_engine/config/social_world/nodes/personas")
             if config_path.exists():
                 for f in config_path.rglob("*.yaml"):
                     try:
                         d = yaml.safe_load(f.read_text())
                         if d.get('id') == active_persona:
                             persona_data = d
                             break
                         if "personas" in d:
                             for p in d["personas"]:
                                 if p.get('id') == active_persona:
                                     persona_data = p
                                     break
                     except: pass
        
        # Calculate Constants for V2
        constants = self._extract_constants(persona_data)

        # Get Domain (V1 static or V2 dynamic)
        domain = self.get_domain(mode, persona_data, constants)
        
        if mode == "social":
            # Auto-construct dynamic state from player if not provided
            if dynamic_state is None:
                dynamic_state = {
                    "current_context": None, 
                    "concepts": list(player_state.known_facts) if hasattr(player_state, 'known_facts') else [],
                }

            # Goal Extraction with Support for Custom/Visual Goals
            import re
            match = re.search(r'\(in-context\s+\w+\s+(\w+)\)', goal_pddl)
            custom_goal = None
            
            if match:
                goal_context_id = match.group(1)
            else:
                # Fallback Logic + Custom Goal Support
                match_v = re.search(r'\(visited\s+(\w+)\)', goal_pddl)
                if match_v:
                     goal_context_id = match_v.group(1)
                elif goal_pddl.strip().startswith("("):
                     # Likely a raw PDDL goal like (visual-event-triggered ...)
                     custom_goal = goal_pddl
                     goal_context_id = "ctx_core" # Dummy, won't be used by template if custom_goal is present
                else:
                     goal_context_id = "ctx_core"

            problem = self.assemble_social_problem(
                player_state.player_id, 
                goal_context_id, 
                dynamic_state, 
                "npc_engine/config/social_world", 
                active_persona,
                custom_goal=custom_goal,
                constants=constants # Pass constants to exclude from Objects
            )
        else:
            problem = self.assemble_problem(mode, player_state, world_graph, goal_pddl)
        
        world_level = get_component_level('world')
        logger.info(f"World level: {world_level}")
        if world_level == 'DEBUG':
            logger.info("DEBUG mode detected, saving PDDL files")
            self._save_pddl_files(player_state.player_id, domain, problem, mode)
        
        return domain, problem

    def _save_pddl_files(self, player_id: str, domain: str, problem: str, mode: str):
        output_dir = Path("generated/pddl")
        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = f"planning_{player_id}_{mode}"
        domain_file = output_dir / f"{base_name}_domain.pddl"
        problem_file = output_dir / f"{base_name}_problem.pddl"
        
        try:
            with open(domain_file, 'w', encoding='utf-8') as f:
                f.write(domain)
            with open(problem_file, 'w', encoding='utf-8') as f:
                f.write(problem)
            logger.info(f"Saved PDDL files: {domain_file}, {problem_file}")
        except Exception as e:
            logger.warning(f"Failed to save PDDL files: {e}")

    def assemble_social_problem(self, player_id: str, goal_context_id: str, dynamic_state: Dict[str, Any] = None, config_dir: str = "npc_engine/config/social_world", active_persona: str = None, custom_goal: str = None, constants: Dict[str, Set[str]] = None) -> str:
        assembler = SocialWorldAssembler(config_path=Path(config_dir), logger=logger)
        personas, target_atlas, target_persona_data = assembler.load_persona_bundle(active_persona)
        contexts, concepts, triggers = assembler.load_world_data(target_atlas, target_persona_data)

        if active_persona:
            assembler.apply_persona_overrides(contexts, active_persona, personas)

        domain_tags = constants.get("tags", set()) if constants else set()
        domain_moods = constants.get("moods", set()) if constants else set()

        objects = assembler.build_social_objects(
            player_id=player_id,
            contexts=contexts,
            concepts=concepts,
            triggers=triggers,
            target_persona_data=target_persona_data,
            active_persona=active_persona,
            domain_tags=domain_tags,
        )

        # Add dynamic inventory items (if provided in dynamic_state)
        extra_items = set()
        if dynamic_state and dynamic_state.get("items"):
            extra_items = set(dynamic_state["items"])
            for item_id in extra_items:
                objects.append(f"{item_id} - item")

        init_facts = assembler.build_social_init_facts(
            player_id=player_id,
            goal_context_id=goal_context_id,
            contexts=contexts,
            triggers=triggers,
            dynamic_state=dynamic_state,
            target_persona_data=target_persona_data,
            active_persona=active_persona,
            domain_moods=domain_moods,
            objects=objects,
        )

        # Inject has-item facts for dynamic inventory
        if extra_items:
            for item_id in extra_items:
                init_facts.append(f"(has-item {player_id} {item_id})")

        return self.renderer.render(
            "social/problem.pddl.j2",
            {
                "objects": objects,
                "init_facts": init_facts,
                "goal_context_id": goal_context_id,
                "custom_goal": custom_goal,
            },
        )

    # === Helper methods for social world assembly (migrated to pddl_libs) ===
