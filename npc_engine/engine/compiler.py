"""Domain compiler: YAML → typed graph objects, validated at startup.

Replaces the ad-hoc YAML loading scattered across pddl_libs.py, pddl_orchestrator.py
and main_fast_ent.py with a single compile-once pass that:
  1. Parses every persona YAML into strongly-typed objects.
  2. Validates referential integrity (missing ctx IDs, unknown concept refs).
  3. Pre-builds the transition index used by DialogueEngine for O(k) move lookup.

Classes
-------
ConfigError           – raised when a config file violates referential integrity.
TransitionCondition   – gate on a context-to-context edge.
DialogueTransition    – one directed edge in the dialogue graph.
CompiledContext       – a context node with its outgoing transitions.
CompiledTrigger       – a trigger node that yields a concept on activation.
CompiledBehaviorRule  – V2 mood+equipment based behaviour action.
CompiledDialogueGraph – full compiled graph for one persona.
DomainCompiler        – entry point: compile_persona / compile_all.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """Raised when a persona YAML fails referential-integrity validation."""


# ---------------------------------------------------------------------------
# Value objects (all frozen)
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class TransitionCondition:
    """Gate that must be satisfied before a context transition is allowed."""

    required_concept: str | None = None
    required_combo: tuple[str, ...] = ()
    required_item: str | None = None

    @property
    def is_unconditional(self) -> bool:
        return (
            self.required_concept is None
            and not self.required_combo
            and self.required_item is None
        )


@dataclasses.dataclass(frozen=True)
class DialogueTransition:
    """One directed edge: from_ctx → to_ctx, with an optional gate."""

    from_ctx: str
    to_ctx: str
    condition: TransitionCondition
    direction: str  # "forward" | "backward" | "bidirectional"


@dataclasses.dataclass(frozen=True)
class CompiledContext:
    """A context node with its outgoing transitions pre-computed."""

    ctx_id: str
    name: str
    description: str
    is_start: bool
    is_locked: bool
    provides_concept: str | None
    induces_mood: str
    transitions: tuple[DialogueTransition, ...]   # outgoing edges

    @property
    def is_goal_candidate(self) -> bool:
        """True when context is locked — typically the social goal."""
        return self.is_locked


@dataclasses.dataclass(frozen=True)
class CompiledTrigger:
    """A trigger that fires in a specific context and yields a concept."""

    trigger_id: str
    name: str
    parent_context: str
    yields: str | None           # concept_id granted on activation; None = pure narrative


@dataclasses.dataclass(frozen=True)
class CompiledBehaviorRule:
    """A V2 mood+equipment conditional action for narrative variety.

    Rules are matched at runtime against the player's current_mood and the
    persona's equipment tags. They produce a ``do_{rule_id}`` move string
    but have NO effect on SocialState (pure narrative).
    """

    rule_id: str
    mood: str                            # required mood ("neutral", "angry", …)
    requires_holding_tag: str | None
    requires_wearing_tag: str | None
    requires_empty_hands: bool
    narrative_template: str
    # Pre-resolved item_id for the required tag (None if no tag required)
    resolved_item_id: str | None


@dataclasses.dataclass(frozen=True)
class CompiledDialogueGraph:
    """Fully compiled and validated dialogue graph for one persona."""

    persona_id: str
    persona_name: str
    contexts: dict[str, CompiledContext]                      # ctx_id → node
    concepts: frozenset[str]                                   # all concept IDs known to this persona
    triggers: dict[str, CompiledTrigger]                      # trigger_id → node
    behavior_rules: tuple[CompiledBehaviorRule, ...]          # V2 mood-based actions
    equipment_tags: frozenset[str]                             # all pddl_tags across all equipment
    start_context: str
    transitions: dict[str, tuple[DialogueTransition, ...]]    # from_ctx → edges
    persona_tags: frozenset[str]                               # persona-level tags (e.g. "proactive")

    def get_transitions(self, ctx_id: str) -> tuple[DialogueTransition, ...]:
        return self.transitions.get(ctx_id, ())

    def get_triggers_for(self, ctx_id: str) -> list[CompiledTrigger]:
        return [t for t in self.triggers.values() if t.parent_context == ctx_id]

    def get_behavior_rules_for_mood(self, mood: str) -> list[CompiledBehaviorRule]:
        return [r for r in self.behavior_rules if r.mood == mood]


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

class DomainCompiler:
    """Compile persona YAML files into validated CompiledDialogueGraph objects.

    Usage::

        compiler = DomainCompiler()
        graphs = compiler.compile_all("npc_engine/config")
        # graphs: dict[persona_id, CompiledDialogueGraph]
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compile_all(self, config_dir: str | Path) -> dict[str, CompiledDialogueGraph]:
        """Compile every persona YAML in config_dir/social_world/nodes/personas/.

        Returns a mapping of persona_id → CompiledDialogueGraph.
        Logs warnings for personas that fail compilation so a single bad file
        does not prevent the rest from loading.
        """
        config_dir = Path(config_dir)
        persona_dir = config_dir / "social_world" / "nodes" / "personas"

        graphs: dict[str, CompiledDialogueGraph] = {}
        if not persona_dir.exists():
            logger.warning(f"Persona directory not found: {persona_dir}")
            return graphs

        for yaml_path in sorted(persona_dir.rglob("*.yaml")):
            try:
                file_graphs = self.compile_persona_file(yaml_path)
                for g in file_graphs:
                    if g.persona_id in graphs:
                        logger.warning(
                            f"Duplicate persona_id '{g.persona_id}' in {yaml_path}; "
                            "overwriting earlier definition."
                        )
                    graphs[g.persona_id] = g
                    logger.info(f"Compiled persona '{g.persona_id}' from {yaml_path.name}")
            except ConfigError as exc:
                logger.error(f"Config error in {yaml_path}: {exc}")
            except Exception as exc:
                logger.error(f"Unexpected error compiling {yaml_path}: {exc}", exc_info=True)

        return graphs

    def compile_persona_file(self, yaml_path: str | Path) -> list[CompiledDialogueGraph]:
        """Load one YAML file and compile all personas found in it.

        Supports both atlas format (type: persona_group with personas list)
        and standalone format (single persona at root).
        """
        yaml_path = Path(yaml_path)
        raw: dict[str, Any] = yaml.safe_load(yaml_path.read_text())
        if not raw:
            return []

        # Collect atlas-level concepts (available to all personas in this file)
        atlas_concepts: set[str] = self._collect_concept_ids(raw.get("concepts", []))

        # Determine persona list
        if raw.get("type") == "persona_group" or "personas" in raw:
            persona_list: list[dict[str, Any]] = raw.get("personas", [])
        else:
            # Standalone: the root IS the persona
            persona_list = [raw]

        graphs = []
        for persona_raw in persona_list:
            g = self._compile_one_persona(persona_raw, atlas_concepts, yaml_path)
            graphs.append(g)

        return graphs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compile_one_persona(
        self,
        persona_raw: dict[str, Any],
        atlas_concepts: set[str],
        source_path: Path,
    ) -> CompiledDialogueGraph:
        persona_id: str = persona_raw.get("id", "")
        if not persona_id:
            raise ConfigError(f"Persona missing 'id' field in {source_path}")

        persona_name: str = persona_raw.get("name", persona_id)

        # --- Collect all concepts known to this persona ---
        persona_concepts = self._collect_concept_ids(persona_raw.get("concepts", []))
        all_concepts = atlas_concepts | persona_concepts

        # --- Parse contexts ---
        ctx_raws: list[dict] = persona_raw.get("contexts", [])
        ctx_ids: set[str] = {c["id"] for c in ctx_raws if "id" in c}

        contexts: dict[str, CompiledContext] = {}
        raw_transitions: list[tuple[str, dict]] = []  # (from_ctx_id, connection_dict)

        start_ctx: str | None = None
        for ctx_raw in ctx_raws:
            ctx_id = ctx_raw.get("id")
            if not ctx_id:
                raise ConfigError(f"[{persona_id}] Context missing 'id' field.")

            props: dict = ctx_raw.get("properties", {})
            if props.get("is_start"):
                start_ctx = ctx_id

            # Collect connections for second-pass transition building
            for conn in ctx_raw.get("connections", []):
                raw_transitions.append((ctx_id, conn))

            # Validate required_concept for locked contexts
            req_concept = props.get("required_concept")
            if req_concept and req_concept not in all_concepts:
                raise ConfigError(
                    f"[{persona_id}] Context '{ctx_id}' requires concept '{req_concept}' "
                    f"which is not defined in this persona file."
                )

            # Validate required_combo
            for combo_cpt in props.get("required_combo", []):
                if combo_cpt not in all_concepts:
                    raise ConfigError(
                        f"[{persona_id}] Context '{ctx_id}' required_combo references "
                        f"unknown concept '{combo_cpt}'."
                    )

            condition = TransitionCondition(
                required_concept=req_concept,
                required_combo=tuple(props.get("required_combo", [])),
                required_item=props.get("required_item"),
            )

            contexts[ctx_id] = CompiledContext(
                ctx_id=ctx_id,
                name=ctx_raw.get("name", ctx_id),
                description=ctx_raw.get("description", ""),
                is_start=bool(props.get("is_start")),
                is_locked=bool(props.get("is_locked")),
                provides_concept=props.get("provides_concept"),
                induces_mood=props.get("induces_mood", ""),
                transitions=(),   # filled in below
            )

        if start_ctx is None and contexts:
            # Fall back to first context
            start_ctx = next(iter(contexts))

        if not start_ctx:
            raise ConfigError(f"[{persona_id}] No contexts defined.")

        # --- Build transitions (second pass so all ctx IDs are known) ---
        transition_map: dict[str, list[DialogueTransition]] = {cid: [] for cid in ctx_ids}

        for from_ctx, conn in raw_transitions:
            to_ctx = conn.get("to")
            if not to_ctx:
                raise ConfigError(f"[{persona_id}] Connection from '{from_ctx}' missing 'to' field.")
            if to_ctx not in ctx_ids:
                raise ConfigError(
                    f"[{persona_id}] Context '{from_ctx}' has connection to unknown "
                    f"context '{to_ctx}'. Known contexts: {sorted(ctx_ids)}"
                )

            direction = conn.get("direction", "forward")
            # The condition on the DESTINATION context (what gates entry into to_ctx)
            dest_props = contexts[to_ctx]
            condition = TransitionCondition(
                required_concept=dest_props.is_locked and dest_props.ctx_id and
                                 contexts[to_ctx].provides_concept or None,
            )
            # Re-derive from raw context props for accuracy
            dest_ctx_raw = next(
                (c for c in persona_raw.get("contexts", []) if c.get("id") == to_ctx), {}
            )
            dest_raw_props = dest_ctx_raw.get("properties", {})
            condition = TransitionCondition(
                required_concept=dest_raw_props.get("required_concept"),
                required_combo=tuple(dest_raw_props.get("required_combo", [])),
                required_item=dest_raw_props.get("required_item"),
            )

            t = DialogueTransition(
                from_ctx=from_ctx,
                to_ctx=to_ctx,
                condition=condition,
                direction=direction,
            )
            transition_map[from_ctx].append(t)

            # Bidirectional: also add the reverse edge
            if direction == "bidirectional":
                rev_dest_ctx_raw = next(
                    (c for c in persona_raw.get("contexts", []) if c.get("id") == from_ctx), {}
                )
                rev_raw_props = rev_dest_ctx_raw.get("properties", {})
                rev_condition = TransitionCondition(
                    required_concept=rev_raw_props.get("required_concept"),
                    required_combo=tuple(rev_raw_props.get("required_combo", [])),
                    required_item=rev_raw_props.get("required_item"),
                )
                rev_t = DialogueTransition(
                    from_ctx=to_ctx,
                    to_ctx=from_ctx,
                    condition=rev_condition,
                    direction="bidirectional",
                )
                transition_map.setdefault(to_ctx, []).append(rev_t)

        # Attach frozen transitions to context nodes
        updated_contexts: dict[str, CompiledContext] = {}
        for ctx_id, ctx in contexts.items():
            updated_contexts[ctx_id] = dataclasses.replace(
                ctx,
                transitions=tuple(transition_map.get(ctx_id, [])),
            )

        frozen_transition_map: dict[str, tuple[DialogueTransition, ...]] = {
            k: tuple(v) for k, v in transition_map.items()
        }

        # --- Parse triggers ---
        triggers: dict[str, CompiledTrigger] = {}
        for trig_raw in persona_raw.get("triggers", []):
            trig_id = trig_raw.get("id")
            if not trig_id:
                raise ConfigError(f"[{persona_id}] Trigger missing 'id' field.")

            parent_ctx = trig_raw.get("parent_context")
            if parent_ctx and parent_ctx not in ctx_ids:
                raise ConfigError(
                    f"[{persona_id}] Trigger '{trig_id}' references unknown "
                    f"parent_context '{parent_ctx}'."
                )

            yields_concept = trig_raw.get("yields")
            if yields_concept and yields_concept not in all_concepts:
                raise ConfigError(
                    f"[{persona_id}] Trigger '{trig_id}' yields unknown "
                    f"concept '{yields_concept}'. Known: {sorted(all_concepts)}"
                )

            triggers[trig_id] = CompiledTrigger(
                trigger_id=trig_id,
                name=trig_raw.get("name", trig_id),
                parent_context=parent_ctx or "",
                yields=yields_concept,
            )

        # --- Parse equipment: collect tags and build tag→item_id index ---
        equipment_tags: set[str] = set()
        tag_to_item_id: dict[str, str] = {}  # first item found wins for each tag

        for _category, items in persona_raw.get("equipment", {}).items():
            if not isinstance(items, list):
                continue
            for item in items:
                item_id = item.get("id", "")
                for tag in item.get("pddl_tags", []):
                    equipment_tags.add(tag)
                    if tag not in tag_to_item_id and item_id:
                        tag_to_item_id[tag] = item_id

        # --- Parse behavior_rules ---
        behavior_rules_list: list[CompiledBehaviorRule] = []
        for rule_raw in persona_raw.get("behavior_rules", []):
            rule_id = rule_raw.get("id")
            if not rule_id:
                raise ConfigError(f"[{persona_id}] behavior_rule missing 'id' field.")

            holding_tag = rule_raw.get("requires_holding_tag")
            wearing_tag = rule_raw.get("requires_wearing_tag")
            empty_hands = bool(rule_raw.get("requires_empty_hands", False))

            # Resolve which item satisfies the required tag (for template substitution)
            resolved_item_id: str | None = None
            if holding_tag:
                resolved_item_id = tag_to_item_id.get(holding_tag)
            elif wearing_tag:
                resolved_item_id = tag_to_item_id.get(wearing_tag)

            behavior_rules_list.append(CompiledBehaviorRule(
                rule_id=rule_id,
                mood=rule_raw.get("mood", "neutral"),
                requires_holding_tag=holding_tag,
                requires_wearing_tag=wearing_tag,
                requires_empty_hands=empty_hands,
                narrative_template=rule_raw.get("narrative_template", ""),
                resolved_item_id=resolved_item_id,
            ))

        # --- Parse persona-level tags ---
        persona_tags_raw = persona_raw.get("tags", [])
        persona_tags: frozenset[str] = frozenset(
            t for t in persona_tags_raw if isinstance(t, str)
        )

        return CompiledDialogueGraph(
            persona_id=persona_id,
            persona_name=persona_name,
            contexts=updated_contexts,
            concepts=frozenset(all_concepts),
            triggers=triggers,
            behavior_rules=tuple(behavior_rules_list),
            equipment_tags=frozenset(equipment_tags),
            start_context=start_ctx,
            transitions=frozen_transition_map,
            persona_tags=persona_tags,
        )

    @staticmethod
    def _collect_concept_ids(concepts_raw: list[dict]) -> set[str]:
        """Extract concept IDs from a list of concept dicts."""
        ids: set[str] = set()
        for c in concepts_raw or []:
            if isinstance(c, dict) and "id" in c:
                ids.add(c["id"])
        return ids
