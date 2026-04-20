"""Async quest planner with TTL plan cache.

Wraps the synchronous PDDL pipeline in a thread-pool executor so the
FastAPI event loop is never blocked during PDDL solving.

Classes
-------
PlanCacheKey    – immutable cache key (player_id, goal, oracle_mode)
QuestPlan       – result object returned by plan_quest()
PlanCache       – simple TTL LRU cache backed by an insertion-order dict
QuestPlanner    – async façade: plan_quest / assess_difficulty / compute_oracle_path
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from npc_engine.engine.compiler import CompiledDialogueGraph
    from npc_engine.engine.world.graph import WorldGraph
    from npc_engine.engine.world.player_state import PlayerState
    from npc_engine.engine.dialogue.state import SocialState

logger = logging.getLogger(__name__)

# Dedicated thread pool — PDDL solving is CPU-bound + subprocess I/O
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="quest-planner")


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class PlanCacheKey:
    """Immutable lookup key for the plan cache."""
    player_id: str
    goal: str
    oracle_mode: bool
    current_location: str = ""
    inventory_signature: tuple[tuple[str, int], ...] = dataclasses.field(default_factory=tuple)


@dataclasses.dataclass
class QuestPlan:
    """Result of a planning call."""
    steps: list[str]            # PDDL plan steps as strings
    quest_steps: list[dict]     # narrative quest steps from QuestGenerator
    error: str | None           # diagnosis message when planning fails
    goal: str
    cached: bool = False        # True when served from cache


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class PlanCache:
    """TTL LRU cache backed by an insertion-order dict.

    Eviction policy:
    - Expired entries are removed lazily on ``get``.
    - When full, the oldest inserted entry is evicted on ``set``.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: float = 300.0) -> None:
        self._store: dict[PlanCacheKey, tuple[QuestPlan, float]] = {}
        self.max_size = max_size
        self.ttl = ttl_seconds

    def get(self, key: PlanCacheKey) -> QuestPlan | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        plan, ts = entry
        if time.monotonic() - ts > self.ttl:
            del self._store[key]
            return None
        return plan

    def set(self, key: PlanCacheKey, plan: QuestPlan) -> None:
        if len(self._store) >= self.max_size:
            # Evict the oldest (first) entry
            oldest = next(iter(self._store))
            del self._store[oldest]
        self._store[key] = (plan, time.monotonic())

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class QuestPlanner:
    """Async façade over the synchronous PDDL solve pipeline.

    All heavy operations run in _EXECUTOR so the event loop stays free.

    Usage::

        planner = QuestPlanner(world)
        plan = await planner.plan_quest(player, goal, oracle_mode=True)
        diff = await planner.assess_difficulty(player)
        path = await planner.compute_oracle_path(state, graph)
    """

    def __init__(
        self,
        world: "WorldGraph",
        cache: PlanCache | None = None,
        oracle_cache: PlanCache | None = None,
    ) -> None:
        self.world = world
        self._cache = cache or PlanCache(max_size=1000, ttl_seconds=300.0)
        self._oracle_cache = oracle_cache or PlanCache(max_size=200, ttl_seconds=600.0)

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def plan_quest(
        self,
        player: "PlayerState",
        goal: str,
        oracle_mode: bool = False,
    ) -> QuestPlan:
        """Plan a quest asynchronously, serving from cache when available."""
        key = PlanCacheKey(
            player_id=player.player_id,
            goal=goal,
            oracle_mode=oracle_mode,
            current_location=getattr(player, "current_location", "") or "",
            inventory_signature=self._inventory_signature(player),
        )
        cached = self._cache.get(key)
        if cached is not None:
            logger.debug("QuestPlanner cache hit: %s / %s", player.player_id, goal)
            return dataclasses.replace(cached, cached=True)

        loop = asyncio.get_event_loop()
        plan = await loop.run_in_executor(
            _EXECUTOR,
            self._solve_sync,
            player,
            goal,
            oracle_mode,
        )
        self._cache.set(key, plan)
        return plan

    async def assess_difficulty(
        self,
        player: "PlayerState",
        world: "WorldGraph | None" = None,
    ) -> str:
        """Return quest difficulty concept, non-blocking.

        Returns one of: ``cpt_quest_easy`` | ``cpt_quest_hard`` | ``cpt_quest_none``
        """
        if not getattr(player, "goal", None):
            return "cpt_quest_none"
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _EXECUTOR,
            self._assess_sync,
            player,
            world or self.world,
        )

    async def compute_oracle_path(
        self,
        state: "SocialState",
        graph: "CompiledDialogueGraph",
    ) -> tuple[str, ...]:
        """BFS oracle path from current_context to goal_context via FSM.

        Returns tuple of PDDL move strings representing the shortest path,
        or empty tuple if goal is unreachable.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _EXECUTOR,
            self._oracle_path_sync,
            state,
            graph,
        )

    # ------------------------------------------------------------------
    # Synchronous internals — run inside thread executor
    # ------------------------------------------------------------------

    def _solve_sync(
        self,
        player: "PlayerState",
        goal: str,
        oracle_mode: bool,
    ) -> QuestPlan:
        from npc_engine.fastapi_ent_libs import generate_plan_and_quest
        try:
            plan_result, quest_steps, error_msg = generate_plan_and_quest(
                self.world, player, goal, oracle_mode
            )
            return QuestPlan(
                steps=plan_result or [],
                quest_steps=quest_steps or [],
                error=error_msg or None,
                goal=goal,
            )
        except Exception as exc:
            logger.error("QuestPlanner._solve_sync error: %s", exc, exc_info=True)
            return QuestPlan(steps=[], quest_steps=[], error=str(exc), goal=goal)

    def _inventory_signature(self, player: "PlayerState") -> tuple[tuple[str, int], ...]:
        inventory = getattr(player, "inventory", None)
        if inventory is None:
            return tuple()
        items = getattr(inventory, "items", {})
        if not isinstance(items, dict):
            return tuple()
        normalized = []
        for item_id, count in items.items():
            try:
                normalized.append((str(item_id), int(count)))
            except Exception:
                normalized.append((str(item_id), 0))
        return tuple(sorted(normalized))

    def _assess_sync(
        self,
        player: "PlayerState",
        world: "WorldGraph",
    ) -> str:
        from npc_engine.engine.master.hooks.registry import execute_hook
        try:
            result = execute_hook("analyze_quest_difficulty", player, world)
            return result or "cpt_quest_none"
        except Exception as exc:
            logger.error("QuestPlanner._assess_sync error: %s", exc, exc_info=True)
            return "cpt_quest_none"

    def _oracle_path_sync(
        self,
        state: "SocialState",
        graph: "CompiledDialogueGraph",
    ) -> tuple[str, ...]:
        from npc_engine.engine.dialogue.engine import DialogueEngine
        engine = DialogueEngine(graph)
        path: list[str] = []
        cur_state = state
        visited: set[str] = set()
        for _ in range(50):   # safety cap
            if engine.is_goal_reached(cur_state):
                break
            if cur_state.current_context in visited:
                break
            visited.add(cur_state.current_context)
            move = engine.get_oracle_next_step(cur_state)
            if move is None:
                break
            path.append(move.pddl_str)
            cur_state = engine.apply_move(move, cur_state)
        return tuple(path)
