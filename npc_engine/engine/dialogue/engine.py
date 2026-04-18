"""Dialogue FSM engine — typed moves, pure state transitions, compiled graph.

Replaces MoveValidator + StateManager with a pure-function engine that
operates on an immutable SocialState + a pre-compiled CompiledDialogueGraph.

Every public method is stateless: it accepts state, returns new state or a
list of moves. The engine itself holds only a reference to the compiled graph.

Classes
-------
DialogueMove   – typed, validated move object
DialogueEngine – move generation, application, goal check, oracle BFS
"""

from __future__ import annotations

import dataclasses
import logging
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from npc_engine.engine.compiler import CompiledDialogueGraph

from npc_engine.engine.dialogue.state import SocialState

logger = logging.getLogger(__name__)

PLAYER = "player"


# ---------------------------------------------------------------------------
# Move object
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class DialogueMove:
    """Typed, validated move in the dialogue FSM.

    ``kind`` is a short category label.  ``pddl_str`` is the full PDDL
    action string preserved for backward-compatibility with the LLM prompt
    layer that currently lists raw move strings.

    Kind taxonomy
    -------------
    shift-context        – free navigation to an adjacent context
    learn-concept        – absorb the concept provided by current context
    activate-trigger     – fire a trigger (yields a concept, marks exhausted)
    apply-concept        – use one concept key to unlock + enter a locked ctx
    apply-combo-concept  – use two concept keys to unlock + enter a locked ctx
    npc-offer            – NPC-initiated concept grant (proactive behaviour)
    npc-flirt            – NPC-initiated flirt variant (proactive behaviour)
    do-behavior          – V2 mood/equipment-gated narrative action (pure narrative)
    """

    kind: str       # see taxonomy above
    pddl_str: str   # full PDDL action string for LLM / planner

    # Kind-specific fields — None when not applicable for this kind
    to_ctx: str | None = None
    concept: str | None = None
    combo: tuple[str, str] | None = None
    trigger_id: str | None = None
    rule_id: str | None = None

    def __str__(self) -> str:
        return self.pddl_str


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DialogueEngine:
    """Pure-function FSM over a CompiledDialogueGraph + SocialState.

    The engine holds no mutable state — all methods accept a SocialState and
    return either a new SocialState or a list of DialogueMoves.

    Usage::

        engine = DialogueEngine(compiled_graph)
        moves  = engine.get_valid_moves(state)
        state  = engine.apply_move(moves[0], state)
        if engine.is_goal_reached(state):
            ...
        hint = engine.get_oracle_next_step(state)
    """

    def __init__(self, graph: "CompiledDialogueGraph") -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_valid_moves(self, state: SocialState) -> list[DialogueMove]:
        """Return all valid moves from the current state.

        Move categories generated (in order):
          1. Context shifts / concept unlocks (outgoing transitions)
          2. Concept learning from the current context
          3. Trigger activations for the current context
          4. V2 mood-gated behavior actions
        """
        moves: list[DialogueMove] = []
        ctx_id = state.current_context

        # 1. Transitions — shift-context, apply-concept, apply-combo-concept
        for t in self.graph.get_transitions(ctx_id):
            to_ctx = t.to_ctx
            dest = self.graph.contexts.get(to_ctx)
            if dest is None:
                continue

            if dest.is_locked and to_ctx not in state.unlocked_contexts:
                # Locked context — emit unlock moves if player holds the key(s)
                cond = t.condition

                if cond.required_concept and cond.required_concept in state.concepts:
                    pddl = (
                        f"apply-concept {PLAYER} {ctx_id} {to_ctx} "
                        f"{cond.required_concept}"
                    )
                    moves.append(DialogueMove(
                        kind="apply-concept",
                        pddl_str=pddl,
                        to_ctx=to_ctx,
                        concept=cond.required_concept,
                    ))

                if len(cond.required_combo) == 2:
                    c1, c2 = cond.required_combo
                    if c1 in state.concepts and c2 in state.concepts:
                        pddl = (
                            f"apply-combo-concept {PLAYER} {ctx_id} {to_ctx} "
                            f"{c1} {c2}"
                        )
                        moves.append(DialogueMove(
                            kind="apply-combo-concept",
                            pddl_str=pddl,
                            to_ctx=to_ctx,
                            combo=(c1, c2),
                        ))
            else:
                # Free navigation (unlocked or not locked)
                pddl = f"shift-context {PLAYER} {ctx_id} {to_ctx}"
                moves.append(DialogueMove(
                    kind="shift-context",
                    pddl_str=pddl,
                    to_ctx=to_ctx,
                ))

        # 2. Concept learning from current context
        current_ctx = self.graph.contexts.get(ctx_id)
        if current_ctx and current_ctx.provides_concept:
            concept = current_ctx.provides_concept
            if concept not in state.concepts:
                pddl = f"learn-concept {PLAYER} {ctx_id} {concept}"
                moves.append(DialogueMove(
                    kind="learn-concept",
                    pddl_str=pddl,
                    concept=concept,
                ))

        # 3. Trigger activations for current context
        for trig in self.graph.get_triggers_for(ctx_id):
            if trig.trigger_id in state.exhausted_triggers:
                continue
            if trig.yields and trig.yields in state.concepts:
                continue
            yields_arg = trig.yields or "none"
            pddl = f"activate-trigger {PLAYER} {ctx_id} {trig.trigger_id} {yields_arg}"
            moves.append(DialogueMove(
                kind="activate-trigger",
                pddl_str=pddl,
                trigger_id=trig.trigger_id,
                concept=trig.yields,
            ))

        # 4. V2 behavior rules — mood-gated, pure narrative
        if state.current_mood:
            for rule in self.graph.get_behavior_rules_for_mood(state.current_mood):
                args = [PLAYER]
                if rule.resolved_item_id:
                    req_tag = (
                        rule.requires_holding_tag
                        or rule.requires_wearing_tag
                        or ""
                    )
                    args += [rule.resolved_item_id, req_tag]
                pddl = f"do_{rule.rule_id} {' '.join(args)}"
                moves.append(DialogueMove(
                    kind="do-behavior",
                    pddl_str=pddl,
                    rule_id=rule.rule_id,
                ))

        return moves

    def apply_move(self, move: DialogueMove, state: SocialState) -> SocialState:
        """Apply a move to state, returning a new SocialState.

        This is a pure function — the incoming state is never mutated.
        """
        if move.kind == "shift-context" and move.to_ctx:
            return self._enter_context(move.to_ctx, state)

        elif move.kind == "learn-concept" and move.concept:
            return state.with_concept(move.concept)

        elif move.kind == "activate-trigger":
            new_state = state
            if move.trigger_id:
                new_state = new_state.with_trigger_exhausted(move.trigger_id)
            if move.concept:
                new_state = new_state.with_concept(move.concept)
            return new_state

        elif move.kind in ("npc-offer", "npc-flirt"):
            if move.concept:
                return state.with_concept(move.concept)
            return state

        elif move.kind == "apply-concept" and move.to_ctx:
            new_state = state.with_context_unlocked(move.to_ctx)
            return self._enter_context(move.to_ctx, new_state)

        elif move.kind == "apply-combo-concept" and move.to_ctx:
            new_state = state.with_context_unlocked(move.to_ctx)
            return self._enter_context(move.to_ctx, new_state)

        elif move.kind == "do-behavior":
            return state  # pure narrative — no state change

        else:
            logger.warning(
                "DialogueEngine.apply_move: unhandled move kind '%s'", move.kind
            )
            return state

    def is_goal_reached(self, state: SocialState) -> bool:
        """Return True if the player has achieved their social goal."""
        if not state.goal_context:
            return False
        return (
            state.current_context == state.goal_context
            or state.goal_context in state.unlocked_contexts
        )

    def get_oracle_next_step(self, state: SocialState) -> DialogueMove | None:
        """BFS over the compiled graph to find the first move toward goal_context.

        The search respects the current player state (concepts, unlocked
        contexts) so it only considers moves that are actually valid.

        Returns the first move on the shortest reachable path to the goal,
        or None if the goal is unreachable from the current state.
        """
        goal = state.goal_context
        if not goal or self.is_goal_reached(state):
            return None

        start = state.current_context

        # Queue entries: (current_ctx, first_move_taken_from_start, current_state)
        visited: set[str] = {start}
        queue: deque[tuple[str, DialogueMove | None, SocialState]] = deque()
        queue.append((start, None, state))

        while queue:
            ctx_id, first_move, cur_state = queue.popleft()

            sim_state = dataclasses.replace(cur_state, current_context=ctx_id)
            for move in self.get_valid_moves(sim_state):
                next_state = self.apply_move(move, sim_state)
                next_ctx = next_state.current_context

                # Check if this move reaches the goal
                if next_ctx == goal or goal in next_state.unlocked_contexts:
                    return first_move if first_move is not None else move

                if next_ctx not in visited:
                    visited.add(next_ctx)
                    queue.append((next_ctx, first_move or move, next_state))

        return None  # Goal not reachable

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _enter_context(self, ctx_id: str, state: SocialState) -> SocialState:
        """Move to ctx_id and apply any mood induction declared by that context."""
        new_state = state.with_context(ctx_id)
        ctx = self.graph.contexts.get(ctx_id)
        if ctx and ctx.induces_mood:
            new_state = new_state.with_mood(ctx.induces_mood)
        return new_state
