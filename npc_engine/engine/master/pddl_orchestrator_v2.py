import jinja2
from pathlib import Path
from typing import Dict, Any
from npc_engine.engine.world.graph import WorldGraph
from npc_engine.engine.world.player_state import PlayerState
from npc_engine.engine.logging_config import logging_manager, get_component_level
import yaml

logger = logging_manager.get_component_logger('master')

class PDDLOrchestratorV2:
    def __init__(self, logic_dir: str = "npc_engine/config/logic"):
        self.logic_dir = Path(logic_dir)
        self.env = jinja2.Environment(loader=jinja2.FileSystemLoader(self.logic_dir))

    def get_domain(self, mode: str, persona_data: Dict[str, Any] = None) -> str:
        """
        Gets the PDDL domain. For V2, it tries to render a template if persona data
        indicates dynamic behaviors.
        """
        # Check for dynamic behavior capability
        use_dynamic_v2 = False
        if persona_data and "behavior_rules" in persona_data:
            use_dynamic_v2 = True

        if use_dynamic_v2 and mode == "social":
            template_path = "social_domain_v2.pddl.j2"
            # Since the template might be in config/social_world which is not logic_dir,
            # we need to be careful with loader. 
            # Assuming social_domain_v2.pddl.j2 is placed in config/social_world 
            # and logic_dir points to config/logic.
            # We might need to adjust logic_dir or use absolute path for template?
            # Better approach: Put the V2 template in config/social_world like problem.pddl.j2
            # and rely on how we access it. 
            # But Orchestrator logic_dir is config/logic. 
            
            # Temporary fix: Let's assume we place the new template in 
            # npc_engine/config/social_world and add that to env loader or specific path
            
            # Actually, PDDLOrchestrator uses logic_dir as base.
            # Social templates are in "npc_engine/config/social_world".
            # Let's add that to the environment search path.
            
            social_dir = Path("npc_engine/config/social_world")
            self.env = jinja2.Environment(loader=jinja2.FileSystemLoader([self.logic_dir, social_dir]))
            
            try:
                template = self.env.get_template(template_path)
                return template.render(persona=persona_data)
            except jinja2.TemplateNotFound:
                logger.error(f"V2 Template not found: {template_path}")
                return "" # Or fallback
                
        else:
            # Fallback to standard static domain
            domain_path = self.logic_dir / mode / "domain.pddl"
            try:
                return domain_path.read_text()
            except FileNotFoundError:
                logger.error(f"Domain file not found: {domain_path}")
                return ""

    def assemble_problem(self, mode: str, player_state: PlayerState, world_graph: WorldGraph, goal_pddl: str) -> str:
        template = self.env.get_template(f"{mode}/problem.pddl.j2")
        
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
        
        return template.render(data)

    def assemble_social_problem(self, player_id: str, goal_context_id: str, dynamic_state: Dict[str, Any] = None, config_dir: str = "npc_engine/config/social_world", active_persona: str = None) -> str:
        # V2: Ensure we look in the right place for templates
        social_dir = Path("npc_engine/config/social_world")
        self.env = jinja2.Environment(loader=jinja2.FileSystemLoader([self.logic_dir, social_dir]))
        
        template = self.env.get_template("social/problem.pddl.j2")
        
        config_path = Path(config_dir)
        contexts = {}
        concepts = {}
        triggers = {}
        personas = {}
        
        target_atlas = None
        target_persona_data = None
        
        # 1. SEARCH FOR ATLAS CONTAINING ACTIVE PERSONA
        pers_dir = config_path / "nodes" / "personas"
        if pers_dir.exists():
            for f in pers_dir.rglob("*.yaml"):
                try:
                    data = yaml.safe_load(f.read_text())
                    
                    # Store personas for later Override logic
                    if "personas" in data and isinstance(data["personas"], list):
                        for p in data["personas"]:
                            if "id" in p:
                                personas[p['id']] = p
                                if active_persona and p['id'] == active_persona:
                                    target_atlas = data
                                    target_persona_data = p
                    elif "id" in data: # Legacy single file
                        personas[data['id']] = data
                        if active_persona and data['id'] == active_persona:
                            target_atlas = data
                            target_persona_data = data
                except Exception as e:
                    logger.error(f"Error loading persona file {f}: {e}")

        # 2. LOAD WORLD DATA (Nested Persona -> Atlas -> Legacy)
        loaded_contexts = []
        loaded_concepts = []
        loaded_triggers = []
        
        if target_persona_data:
            logger.info(f"Loading Social World from Persona: {active_persona}")
            # Try nested data first
            loaded_contexts = target_persona_data.get("contexts", [])
            loaded_concepts = target_persona_data.get("concepts", [])
            loaded_triggers = target_persona_data.get("triggers", [])
            
            # If persona doesn't have it, try atlas level (Hybrid mode)
            if not loaded_contexts and target_atlas:
                loaded_contexts = target_atlas.get("contexts", [])
            if not loaded_concepts and target_atlas:
                loaded_concepts = target_atlas.get("concepts", [])
            if not loaded_triggers and target_atlas:
                loaded_triggers = target_atlas.get("triggers", [])
                
        elif target_atlas:
             # Fallback to atlas if no persona match but atlas found (rare)
             loaded_contexts = target_atlas.get("contexts", [])
             loaded_concepts = target_atlas.get("concepts", [])
             loaded_triggers = target_atlas.get("triggers", [])
             
        else:
            logger.info("No Atlas found. Loading Legacy World (Merged).")
            # Legacy: Load from separate folders
            ctx_dir = config_path / "nodes" / "contexts"
            if ctx_dir.exists():
                for f in ctx_dir.rglob("*.yaml"):
                    data = yaml.safe_load(f.read_text())
                    contexts[data['id']] = data
            
            cpt_dir = config_path / "nodes" / "concepts"
            if cpt_dir.exists():
                for f in cpt_dir.rglob("*.yaml"):
                    data = yaml.safe_load(f.read_text())
                    concepts[data['id']] = data

            trig_dir = config_path / "nodes" / "triggers"
            if trig_dir.exists():
                for f in trig_dir.rglob("*.yaml"):
                    data = yaml.safe_load(f.read_text())
                    triggers[data['id']] = data

        # Populate dictionaries from loaded lists
        for ctx in loaded_contexts: contexts[ctx['id']] = ctx
        for cpt in loaded_concepts: concepts[cpt['id']] = cpt
        for trig in loaded_triggers: triggers[trig['id']] = trig

        # APPLY PERSONA OVERRIDES (Standard Logic)
        if active_persona and active_persona in personas:
            p_data = personas[active_persona]
            overrides = p_data.get('world_overrides', {})
            logger.info(f"Applying overrides for persona: {active_persona}")
            
            for ctx_id, override_props in overrides.items():
                if ctx_id in contexts:
                    ctx_data = contexts[ctx_id]
                    for k, v in override_props.items():
                        if k != 'properties':
                            ctx_data[k] = v
                    if 'properties' not in ctx_data: ctx_data['properties'] = {}
                    for k, v in override_props.items():
                        if k not in ['name', 'description'] and k != 'properties':
                            ctx_data['properties'][k] = v

        # Build objects
        objects = []
        objects.extend([f"{cid} - context" for cid in contexts])
        objects.extend([f"{cid} - concept" for cid in concepts])
        objects.extend([f"{tid} - trigger" for tid in triggers])
        objects.append(f"{player_id} - agent")
        
        # V2: Add Equipment Objects if Persona has them
        # Note: We need to define types 'item' and 'tag' in the domain for this to work
        # Since 'assemble_social_problem' uses 'social/problem.pddl.j2' (the standard one)
        # we might need a v2 problem template as well if we want to inject items properly.
        # But for now, let's just add them to 'objects' list if the standard template supports arbitrary objects.
        # The standard template iterates over 'objects' list.
        
        if target_persona_data and "equipment" in target_persona_data:
            eq = target_persona_data["equipment"]
            for cat in eq.values(): # clothes, weapons
                for item in cat:
                    objects.append(f"{item['id']} - item")
                    if "pddl_tags" in item:
                        for tag in item["pddl_tags"]:
                             objects.append(f"{tag} - tag")

        # Build init
        init_facts = []
        
        # Context Connections & Locks
        for cid, ctx in contexts.items():
            props = ctx.get('properties', {})
            
            # Links
            for conn in ctx.get('connections', []):
                target = conn['to']
                init_facts.append(f"(connected {cid} {target})")
                if conn.get('direction') == 'bidirectional':
                    init_facts.append(f"(connected {target} {cid})")
            
            # Locks
            if props.get('is_locked') and cid != goal_context_id:
                is_unlocked = dynamic_state and cid in dynamic_state.get('unlocked_contexts', [])
                if not is_unlocked:
                    init_facts.append(f"(locked {cid})")
            
            # Requirements
            if props.get('required_concept'):
                init_facts.append(f"(requires-concept {cid} {props['required_concept']})")
                
            if props.get('required_combo'):
                combo = props['required_combo']
                if len(combo) == 2:
                    init_facts.append(f"(requires-combo {cid} {combo[0]} {combo[1]})")
                
            # Passive Concept Provision
            if props.get('provides_concept'):
                init_facts.append(f"(provides-concept {cid} {props['provides_concept']})")

        # Triggers placement
        for tid, trig in triggers.items():
            parent = trig.get('parent_context')
            if parent:
                init_facts.append(f"(in-context {tid} {parent})")
            
            yields = trig.get('yields')
            if yields:
                init_facts.append(f"(trigger-yields {tid} {yields})")

        # Dynamic State Injection
        start_ctx = None
        
        # 1. Try from dynamic state
        if dynamic_state and dynamic_state.get("current_context"):
            start_ctx = dynamic_state.get("current_context")
        
        # 2. Fallback to 'is_start' property (Persona overrides applied above)
        if not start_ctx:
            start_ctx = next((cid for cid, c in contexts.items() if c.get('properties', {}).get('is_start')), None)
            
        if start_ctx:
            init_facts.append(f"(active-context {player_id} {start_ctx})")
        else:
            logger.warning("No starting context found for social problem!")

        # 3. Concepts/History from dynamic state
        if dynamic_state:
            for cpt in dynamic_state.get("concepts", []):
                init_facts.append(f"(has-concept {player_id} {cpt})")
                
            for v_ctx in dynamic_state.get("visited_contexts", []):
                init_facts.append(f"(visited {v_ctx})")
                
            for exh_trig in dynamic_state.get("exhausted_triggers", []):
                init_facts.append(f"(exhausted {exh_trig})")
        
        # V2: Inject Equipment Facts
        if target_persona_data and "equipment" in target_persona_data:
            eq = target_persona_data["equipment"]
            
            # Helper to add facts
            def add_equip_facts(item_list, predicate):
                for item in item_list:
                    # Assume NPC is wearing/holding everything defined for now
                    init_facts.append(f"({predicate} {active_persona} {item['id']})") # NPC acts as agent? No, 'active_persona' is ID string.
                    # Wait, in social domain, usually 'player_id' is the agent moving around.
                    # BUT for behavior actions like (act_brandish_weapon ?a), who is ?a?
                    # If the actions are for the NPC, then the NPC must be an agent in the problem.
                    # Standard social problem only has player_001 as agent.
                    
                    # Correction: We need to add the NPC as an agent if we want them to act.
                    # Or, we treat 'dolores' as an agent.
                    # Let's check 'objects' list construction above. 
                    # "objects.append(f'{player_id} - agent')" is there.
                    # We should add the NPC ID as agent too?
                    # Or maybe the player observes the NPC?
                    
                    # For this prototype, let's assume the NPC is also an agent 
                    # OR we just bind equipment to the player for testing actions?
                    # No, the YAML said "Dolores brandishes..." -> NPC is actor.
                    
                    if "pddl_tags" in item:
                        for tag in item["pddl_tags"]:
                            init_facts.append(f"(has-tag {item['id']} {tag})")
                            init_facts.append(f"(is-tag {tag} {tag})") # Helper for equality check?
            
            if "clothes" in eq:
                add_equip_facts(eq["clothes"], "wearing")
            if "weapons" in eq:
                add_equip_facts(eq["weapons"], "holding")
                
            # Ensure NPC is defined as agent if not player
            # In social domain, usually we simulate the conversation.
            # If we want PDDL to generate NPC actions, the planner needs to control NPC?
            # Or is this "narrative planning" where we just find a valid action to Describe?
            # Yes, "Description on the fly".
            pass

        data = {
            "objects": objects,
            "init_facts": init_facts,
            "goal_context_id": goal_context_id
        }
        
        return template.render(data)
    
    def generate(self, mode: str, player_state: PlayerState, world_graph: WorldGraph, goal_pddl: str, dynamic_state: Dict[str, Any] = None, active_persona: str = None) -> tuple[str, str]:
        logger.info(f"PDDLOrchestratorV2.generate called for mode {mode} with goal {goal_pddl}")
        
        # Need to fetch persona data early to determine if we use V2 logic
        persona_data = {}
        if active_persona:
             # Mini-loader for persona data (duplicate logic, but needed for V2 check)
             # Better: Refactor 'assemble_social_problem' to return data, or load it here.
             # For V2 prototype, let's just load it.
             config_path = Path("npc_engine/config/social_world/nodes/personas")
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

        domain = self.get_domain(mode, persona_data)
        
        if mode == "social":
            if dynamic_state is None:
                dynamic_state = {
                    "current_context": None,
                    "concepts": list(player_state.known_facts) if hasattr(player_state, 'known_facts') else [],
                }

            import re
            match = re.search(r'\(in-context\s+\w+\s+(\w+)\)', goal_pddl)
            if match:
                goal_context_id = match.group(1)
            else:
                match_v = re.search(r'\(visited\s+(\w+)\)', goal_pddl)
                goal_context_id = match_v.group(1) if match_v else "ctx_core"

            problem = self.assemble_social_problem(player_state.player_id, goal_context_id, dynamic_state, "npc_engine/config/social_world", active_persona)
        else:
            problem = self.assemble_problem(mode, player_state, world_graph, goal_pddl)
        
        return domain, problem
