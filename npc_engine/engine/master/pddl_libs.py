from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple
import yaml


@dataclass
class SocialWorldAssembler:
    """Helper for assembling social PDDL objects and facts from persona/world data."""

    config_path: Path
    logger: Any

    def load_persona_bundle(self, active_persona: Optional[str]) -> Tuple[Dict[str, Any], Any, Any]:
        personas = {}
        target_atlas = None
        target_persona_data = None

        pers_dir = self.config_path / "nodes" / "personas"
        if not pers_dir.exists():
            return personas, target_atlas, target_persona_data

        for f in pers_dir.rglob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text())
            except Exception as e:
                self.logger.error(f"Error loading persona file {f}: {e}")
                continue

            if not data:
                continue

            if "personas" in data and isinstance(data["personas"], list):
                for p in data["personas"]:
                    if "id" not in p:
                        continue
                    personas[p['id']] = p
                    if active_persona and p['id'] == active_persona:
                        target_atlas = data
                        target_persona_data = p
            elif "id" in data:
                personas[data['id']] = data
                if active_persona and data['id'] == active_persona:
                    target_atlas = data
                    target_persona_data = data

        return personas, target_atlas, target_persona_data

    def load_world_data(self, target_atlas: Any, target_persona_data: Any) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        contexts = {}
        concepts = {}
        triggers = {}

        def collect_nodes(nodes):
            return {n['id']: n for n in nodes or [] if isinstance(n, dict) and 'id' in n}

        if target_persona_data:
            self.logger.info(f"Loading Social World from Persona: {target_persona_data.get('id')}")
            contexts = collect_nodes(target_persona_data.get("contexts"))
            concepts = collect_nodes(target_persona_data.get("concepts"))
            triggers = collect_nodes(target_persona_data.get("triggers"))

            if not contexts and target_atlas:
                contexts = collect_nodes(target_atlas.get("contexts"))
            if not concepts and target_atlas:
                concepts = collect_nodes(target_atlas.get("concepts"))
            if not triggers and target_atlas:
                triggers = collect_nodes(target_atlas.get("triggers"))
        elif target_atlas:
            contexts = collect_nodes(target_atlas.get("contexts"))
            concepts = collect_nodes(target_atlas.get("concepts"))
            triggers = collect_nodes(target_atlas.get("triggers"))
        else:
            self.logger.info("No Atlas found. Loading Legacy World (Merged).")
            contexts = self._load_legacy_nodes(self.config_path / "nodes" / "contexts", "contexts")
            concepts = self._load_legacy_nodes(self.config_path / "nodes" / "concepts", "concepts")
            triggers = self._load_legacy_nodes(self.config_path / "nodes" / "triggers", "triggers")

        return contexts, concepts, triggers

    def _load_legacy_nodes(self, dir_path: Path, list_key: str) -> Dict[str, Any]:
        data_map = {}
        if not dir_path.exists():
            return data_map

        for f in dir_path.rglob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text())
            except Exception as e:
                self.logger.error(f"Error loading {list_key} file {f}: {e}")
                continue

            if not data:
                continue

            if list_key in data and isinstance(data[list_key], list):
                for item in data[list_key]:
                    if 'id' in item:
                        data_map[item['id']] = item
            elif 'id' in data:
                data_map[data['id']] = data

        return data_map

    def apply_persona_overrides(self, contexts: Dict[str, Any], active_persona: str, personas: Dict[str, Any]) -> None:
        if not active_persona or active_persona not in personas:
            return

        overrides = personas[active_persona].get('world_overrides', {})
        if not overrides:
            return

        self.logger.info(f"Applying overrides for persona: {active_persona}")
        for ctx_id, override_props in overrides.items():
            if ctx_id not in contexts:
                continue
            ctx_data = contexts[ctx_id]
            for k, v in override_props.items():
                if k != 'properties':
                    ctx_data[k] = v
            if 'properties' not in ctx_data:
                ctx_data['properties'] = {}
            for k, v in override_props.items():
                if k not in ['name', 'description'] and k != 'properties':
                    ctx_data['properties'][k] = v

    def build_social_objects(
        self,
        player_id: str,
        contexts: Dict[str, Any],
        concepts: Dict[str, Any],
        triggers: Dict[str, Any],
        target_persona_data: Any,
        active_persona: Optional[str],
        domain_tags: Set[str],
    ) -> list[str]:
        objects = []
        objects.extend([f"{cid} - context" for cid in contexts])
        objects.extend([f"{cid} - concept" for cid in concepts])
        objects.extend([f"{tid} - trigger" for tid in triggers])
        objects.append(f"{player_id} - agent")

        if target_persona_data:
            if "secrets" in target_persona_data:
                for s in target_persona_data["secrets"]:
                    objects.append(f"{s['id']} - secret")
            if "traits" in target_persona_data:
                for t in target_persona_data["traits"]:
                    objects.append(f"{t['id']} - trait")
            if active_persona:
                objects.append(f"{active_persona} - agent")
            if "equipment" in target_persona_data:
                self._add_equipment_objects(target_persona_data["equipment"], objects, domain_tags)

        return objects

    def _add_equipment_objects(self, equipment: Dict[str, Any], objects: list[str], domain_tags: Set[str]) -> None:
        for category in ("clothes", "weapons", "items"):
            for item in equipment.get(category, []) or []:
                objects.append(f"{item['id']} - item")
                for tag in item.get("pddl_tags", []):
                    if tag not in domain_tags:
                        objects.append(f"{tag} - tag")

    def build_social_init_facts(
        self,
        player_id: str,
        goal_context_id: str,
        contexts: Dict[str, Any],
        triggers: Dict[str, Any],
        dynamic_state: Dict[str, Any],
        target_persona_data: Any,
        active_persona: Optional[str],
        domain_moods: Set[str],
        objects: list[str],
    ) -> list[str]:
        init_facts = []

        for cid, ctx in contexts.items():
            props = ctx.get('properties', {})
            for conn in ctx.get('connections', []):
                target = conn['to']
                init_facts.append(f"(connected {cid} {target})")
                if conn.get('direction') == 'bidirectional':
                    init_facts.append(f"(connected {target} {cid})")

            if props.get('is_locked') and cid != goal_context_id:
                is_unlocked = dynamic_state and cid in dynamic_state.get('unlocked_contexts', [])
                if not is_unlocked:
                    init_facts.append(f"(locked {cid})")

            if props.get('required_concept'):
                init_facts.append(f"(requires-concept {cid} {props['required_concept']})")

            if props.get('required_combo'):
                combo = props['required_combo']
                if len(combo) == 2:
                    init_facts.append(f"(requires-combo {cid} {combo[0]} {combo[1]})")

            if props.get('provides_concept'):
                init_facts.append(f"(provides-concept {cid} {props['provides_concept']})")

        for tid, trig in triggers.items():
            parent = trig.get('parent_context')
            if parent:
                init_facts.append(f"(in-context {tid} {parent})")
            yields = trig.get('yields')
            if yields:
                init_facts.append(f"(trigger-yields {tid} {yields})")

        start_ctx = None
        if dynamic_state and dynamic_state.get("current_context"):
            start_ctx = dynamic_state.get("current_context")
        if not start_ctx:
            start_ctx = next((cid for cid, c in contexts.items() if c.get('properties', {}).get('is_start')), None)

        if start_ctx:
            init_facts.append(f"(active-context {player_id} {start_ctx})")
        else:
            self.logger.warning("No starting context found for social problem!")

        if dynamic_state:
            for cpt in dynamic_state.get("concepts", []):
                init_facts.append(f"(has-concept {player_id} {cpt})")
            for v_ctx in dynamic_state.get("visited_contexts", []):
                init_facts.append(f"(visited {v_ctx})")
            for exh_trig in dynamic_state.get("exhausted_triggers", []):
                init_facts.append(f"(exhausted {exh_trig})")

        if target_persona_data and active_persona:
            if "traits" in target_persona_data:
                for t in target_persona_data["traits"]:
                    init_facts.append(f"(has-trait {active_persona} {t['id']})")

            if "secrets" in target_persona_data:
                for s in target_persona_data["secrets"]:
                    if "requires_item" in s:
                        init_facts.append(f"(requires-item {s['id']} {s['requires_item']})")

            if dynamic_state and dynamic_state.get("is_hostile"):
                init_facts.append(f"(is-hostile {active_persona})")

            if "equipment" in target_persona_data:
                self._add_equipment_facts(target_persona_data["equipment"], player_id, init_facts)

        if dynamic_state and dynamic_state.get("current_mood"):
            mood = dynamic_state["current_mood"]
            if mood not in domain_moods:
                objects.append(f"{mood} - mood")
            init_facts.append(f"(current-mood {player_id} {mood})")

        return init_facts

    def _add_equipment_facts(self, equipment: Dict[str, Any], player_id: str, init_facts: list[str]) -> None:
        def add_equip_facts(item_list, predicate):
            for item in item_list:
                init_facts.append(f"({predicate} {player_id} {item['id']})")
                for tag in item.get("pddl_tags", []):
                    init_facts.append(f"(has-tag {item['id']} {tag})")
                    init_facts.append(f"(is-tag {tag} {tag})")

        if "clothes" in equipment:
            add_equip_facts(equipment["clothes"], "wearing")
        if "weapons" in equipment:
            add_equip_facts(equipment["weapons"], "holding")
