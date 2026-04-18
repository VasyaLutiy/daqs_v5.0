"""
Tests for Phase 4 — QuestPlanner async façade (PLAN_2026_APR_14.md).

test_4.1  plan_quest returns a QuestPlan dataclass
test_4.2  impossible goal returns QuestPlan with error set (no exception)
test_4.3  second identical call is served from cache (cached=True)
test_4.4  assess_difficulty returns a non-empty string concept
test_4.5  compute_oracle_path returns a tuple (possibly empty)
test_4.6  plan_quest is non-blocking: two concurrent calls both complete
test_4.7  PlanCache respects TTL — expired entry not returned

Async tests use asyncio.run() so no extra pytest plugins are needed.
"""

from __future__ import annotations

import asyncio
import time
import types
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: stub heavy optional deps
# ---------------------------------------------------------------------------

_dummy_formatter_cls = type(
    "_DummyFormatter",
    (),
    {
        "__init__": lambda self, *a, **kw: None,
        "format": lambda self, r: r.getMessage(),
    },
)

sys.modules.setdefault(
    "coloredlogs",
    types.SimpleNamespace(
        install=lambda *a, **kw: None,
        ColoredFormatter=_dummy_formatter_cls,
    ),
)

_google_stub = types.ModuleType("google")
_genai_stub = types.ModuleType("google.genai")
_google_stub.genai = _genai_stub
sys.modules.setdefault("google", _google_stub)
sys.modules.setdefault("google.genai", _genai_stub)
sys.modules.setdefault("google.genai.types", types.ModuleType("google.genai.types"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from npc_engine.engine.quest.planner import (  # noqa: E402
    PlanCache,
    PlanCacheKey,
    QuestPlan,
    QuestPlanner,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player(player_id: str = "player_001", goal: str = "find_sword") -> MagicMock:
    player = MagicMock()
    player.player_id = player_id
    player.goal = goal
    return player


def _make_world() -> MagicMock:
    return MagicMock()


def _good_plan() -> tuple:
    """Return value that generate_plan_and_quest would produce on success."""
    return (["(move forest_entrance cave)"], [{"step": 1, "desc": "Go to cave"}], None)


def _failed_plan() -> tuple:
    return (None, [], "No plan found for impossible goal")


# ---------------------------------------------------------------------------
# test_4.1 — plan_quest returns QuestPlan dataclass
# ---------------------------------------------------------------------------


def test_4_1_plan_quest_returns_quest_plan():
    async def _run():
        planner = QuestPlanner(world=_make_world())
        player = _make_player()
        with patch.object(
            planner,
            "_solve_sync",
            return_value=QuestPlan(
                steps=["(move a b)"],
                quest_steps=[{"step": 1}],
                error=None,
                goal="find_sword",
            ),
        ):
            return await planner.plan_quest(player, "find_sword")

    result = asyncio.run(_run())
    assert isinstance(result, QuestPlan)
    assert result.goal == "find_sword"
    assert isinstance(result.steps, list)
    assert isinstance(result.quest_steps, list)
    assert result.error is None


# ---------------------------------------------------------------------------
# test_4.2 — impossible goal → QuestPlan.error is set, no exception raised
# ---------------------------------------------------------------------------


def test_4_2_impossible_goal_sets_error():
    async def _run():
        planner = QuestPlanner(world=_make_world())
        player = _make_player(goal="impossible_goal_xyz")
        with patch.object(
            planner,
            "_solve_sync",
            return_value=QuestPlan(
                steps=[],
                quest_steps=[],
                error="No plan found",
                goal="impossible_goal_xyz",
            ),
        ):
            return await planner.plan_quest(player, "impossible_goal_xyz")

    result = asyncio.run(_run())
    assert isinstance(result, QuestPlan)
    assert result.error is not None
    assert result.steps == []


# ---------------------------------------------------------------------------
# test_4.3 — second identical call is served from cache (cached=True)
# ---------------------------------------------------------------------------


def test_4_3_cache_hit_on_second_call():
    call_count = 0

    async def _run():
        nonlocal call_count
        planner = QuestPlanner(world=_make_world())
        player = _make_player()
        base_plan = QuestPlan(steps=["(move a b)"], quest_steps=[], error=None, goal="find_sword")

        def fake_solve(p, g, om):
            nonlocal call_count
            call_count += 1
            return base_plan

        with patch.object(planner, "_solve_sync", side_effect=fake_solve):
            first = await planner.plan_quest(player, "find_sword")
            second = await planner.plan_quest(player, "find_sword")
        return first, second

    first, second = asyncio.run(_run())
    assert call_count == 1, "Solver must be called only once; second call should hit cache"
    assert first.cached is False
    assert second.cached is True


# ---------------------------------------------------------------------------
# test_4.4 — assess_difficulty returns a string concept
# ---------------------------------------------------------------------------


def test_4_4_assess_difficulty_returns_concept():
    async def _run():
        planner = QuestPlanner(world=_make_world())
        player = _make_player()
        player.goal = "find_sword"
        with patch.object(planner, "_assess_sync", return_value="cpt_quest_easy"):
            return await planner.assess_difficulty(player)

    concept = asyncio.run(_run())
    assert isinstance(concept, str)
    assert concept == "cpt_quest_easy"


def test_4_4b_assess_difficulty_no_goal_returns_none():
    async def _run():
        planner = QuestPlanner(world=_make_world())
        player = _make_player()
        player.goal = None
        return await planner.assess_difficulty(player)

    concept = asyncio.run(_run())
    assert concept == "cpt_quest_none"


# ---------------------------------------------------------------------------
# test_4.5 — compute_oracle_path returns tuple
# ---------------------------------------------------------------------------


def test_4_5_oracle_path_returns_tuple():
    async def _run():
        planner = QuestPlanner(world=_make_world())
        state, graph = MagicMock(), MagicMock()
        with patch.object(
            planner,
            "_oracle_path_sync",
            return_value=("(shift-context p ctx_a ctx_b)", "(learn-concept p ctx_b cpt_x)"),
        ):
            return await planner.compute_oracle_path(state, graph)

    path = asyncio.run(_run())
    assert isinstance(path, tuple)
    assert len(path) == 2


def test_4_5b_oracle_path_empty_when_goal_unreachable():
    async def _run():
        planner = QuestPlanner(world=_make_world())
        state, graph = MagicMock(), MagicMock()
        with patch.object(planner, "_oracle_path_sync", return_value=()):
            return await planner.compute_oracle_path(state, graph)

    path = asyncio.run(_run())
    assert path == ()


# ---------------------------------------------------------------------------
# test_4.6 — concurrent calls both complete (non-blocking)
# ---------------------------------------------------------------------------


def test_4_6_concurrent_calls_both_complete():
    async def _run():
        planner = QuestPlanner(world=_make_world())

        async def make_call(player_id: str, goal: str) -> QuestPlan:
            player = _make_player(player_id=player_id, goal=goal)
            plan = QuestPlan(steps=[], quest_steps=[], error=None, goal=goal)
            with patch.object(planner, "_solve_sync", return_value=plan):
                return await planner.plan_quest(player, goal)

        return await asyncio.gather(
            make_call("player_a", "goal_a"),
            make_call("player_b", "goal_b"),
        )

    results = asyncio.run(_run())
    assert len(results) == 2
    assert results[0].goal == "goal_a"
    assert results[1].goal == "goal_b"


# ---------------------------------------------------------------------------
# test_4.7 — PlanCache TTL: expired entry is not returned
# ---------------------------------------------------------------------------


def test_4_7_plan_cache_ttl_expiry():
    cache = PlanCache(max_size=100, ttl_seconds=0.05)  # 50 ms TTL
    key = PlanCacheKey(player_id="p1", goal="find_sword", oracle_mode=False)
    plan = QuestPlan(steps=["(move a b)"], quest_steps=[], error=None, goal="find_sword")

    cache.set(key, plan)
    assert cache.get(key) is not None, "Entry should be live immediately after set"

    time.sleep(0.1)  # outlast the TTL
    assert cache.get(key) is None, "Entry must be expired after TTL"


def test_4_7b_plan_cache_max_size_evicts_oldest():
    cache = PlanCache(max_size=3, ttl_seconds=300.0)

    for i in range(3):
        k = PlanCacheKey(player_id=f"p{i}", goal="g", oracle_mode=False)
        cache.set(k, QuestPlan(steps=[], quest_steps=[], error=None, goal="g"))

    assert len(cache) == 3

    # Adding a 4th entry must evict the oldest (p0)
    k_new = PlanCacheKey(player_id="p3", goal="g", oracle_mode=False)
    cache.set(k_new, QuestPlan(steps=[], quest_steps=[], error=None, goal="g"))

    assert len(cache) == 3
    k_evicted = PlanCacheKey(player_id="p0", goal="g", oracle_mode=False)
    assert cache.get(k_evicted) is None, "Oldest entry must have been evicted"
    assert cache.get(k_new) is not None, "Newest entry must still be present"
