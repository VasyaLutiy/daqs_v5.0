"""
Tests for Phase 6 — SessionStore (PLAN_2026_APR_14.md).

test_6.1  set + get returns correct data
test_6.2  get on missing key returns None
test_6.3  TTL expiry: get after TTL returns None
test_6.4  get_or_create returns existing session without overwriting
test_6.5  get_or_create creates a new entry when key is missing
test_6.6  max_sessions evicts the oldest entry on overflow
test_6.7  sweep_expired removes all stale entries and returns count
test_6.8  concurrent set + get on the same key never corrupts data
test_6.9  touch on get resets TTL (slide-window behaviour)
"""

from __future__ import annotations

import asyncio
import time
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from npc_engine.engine.session_store import SessionStore  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# test_6.1 — set then get returns the stored data
# ---------------------------------------------------------------------------


def test_6_1_set_get_round_trip():
    store = SessionStore()
    data = {"persona_id": "cyber", "concepts": ["cpt_x"]}

    run(store.set("key1", data))
    result = run(store.get("key1"))

    assert result == data
    assert result is data  # same object


# ---------------------------------------------------------------------------
# test_6.2 — get on missing key returns None
# ---------------------------------------------------------------------------


def test_6_2_get_missing_returns_none():
    store = SessionStore()
    assert run(store.get("nonexistent")) is None


# ---------------------------------------------------------------------------
# test_6.3 — TTL expiry: get after TTL returns None, entry is removed
# ---------------------------------------------------------------------------


def test_6_3_ttl_expiry():
    store = SessionStore(ttl_seconds=0.05)  # 50 ms
    run(store.set("k", {"x": 1}))

    assert run(store.get("k")) is not None, "should be live immediately"
    time.sleep(0.1)
    assert run(store.get("k")) is None, "should be expired after TTL"
    assert len(store) == 0, "expired entry must be removed from the store"


# ---------------------------------------------------------------------------
# test_6.4 — get_or_create returns existing session unchanged
# ---------------------------------------------------------------------------


def test_6_4_get_or_create_returns_existing():
    store = SessionStore()
    original = {"history": ["msg1"], "persona_id": "cyber"}
    run(store.set("sess1", original))

    result = run(store.get_or_create("sess1", {"history": [], "persona_id": "OTHER"}))

    assert result["persona_id"] == "cyber"
    assert result["history"] == ["msg1"]


# ---------------------------------------------------------------------------
# test_6.5 — get_or_create creates a new entry when key is absent
# ---------------------------------------------------------------------------


def test_6_5_get_or_create_creates_when_missing():
    store = SessionStore()
    default = {"persona_id": "paladin", "concepts": []}

    result = run(store.get_or_create("new_sess", default))

    assert result is default
    assert len(store) == 1
    assert run(store.get("new_sess")) is default


# ---------------------------------------------------------------------------
# test_6.6 — max_sessions evicts oldest on overflow
# ---------------------------------------------------------------------------


def test_6_6_max_sessions_evicts_oldest():
    store = SessionStore(max_sessions=3, ttl_seconds=300.0)

    for i in range(3):
        run(store.set(f"k{i}", {"i": i}))

    assert len(store) == 3

    # Adding a 4th entry must evict k0 (oldest)
    run(store.set("k3", {"i": 3}))

    assert len(store) == 3
    assert run(store.get("k0")) is None, "oldest entry must have been evicted"
    assert run(store.get("k3")) is not None, "newest entry must be present"


# ---------------------------------------------------------------------------
# test_6.7 — sweep_expired removes all stale entries, returns correct count
# ---------------------------------------------------------------------------


def test_6_7_sweep_expired():
    store = SessionStore(ttl_seconds=0.05, max_sessions=100)

    for i in range(5):
        run(store.set(f"old_{i}", {"v": i}))

    time.sleep(0.1)  # let all 5 expire

    # Add 2 fresh entries
    run(store.set("fresh_a", {"v": "a"}))
    run(store.set("fresh_b", {"v": "b"}))

    removed = run(store.sweep_expired())

    assert removed == 5, f"Expected 5 removed, got {removed}"
    assert len(store) == 2, "Only the 2 fresh entries should remain"
    assert run(store.get("fresh_a")) is not None
    assert run(store.get("fresh_b")) is not None


# ---------------------------------------------------------------------------
# test_6.8 — concurrent set + get never corrupts data
# ---------------------------------------------------------------------------


def test_6_8_concurrent_access_no_corruption():
    """Fire 50 concurrent writers and 50 concurrent readers on 5 keys."""

    async def _run():
        store = SessionStore(ttl_seconds=60.0, max_sessions=1000)
        keys = [f"sess_{i}" for i in range(5)]

        async def writer(key: str, idx: int):
            await store.set(key, {"key": key, "idx": idx})

        async def reader(key: str):
            val = await store.get(key)
            # val may be None if not yet written — that's fine
            if val is not None:
                assert val["key"] == key

        tasks = []
        for i in range(10):
            for k in keys:
                tasks.append(writer(k, i))
                tasks.append(reader(k))

        await asyncio.gather(*tasks)

        # After all operations every key must map to a dict with correct "key" field
        for k in keys:
            val = await store.get(k)
            assert val is not None
            assert val["key"] == k

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# test_6.9 — touch on get resets TTL (slide-window behaviour)
# ---------------------------------------------------------------------------


def test_6_9_touch_on_get_extends_ttl():
    store = SessionStore(ttl_seconds=0.15)
    run(store.set("k", {"x": 1}))

    # Read at ~80 ms — this should refresh the touch timestamp
    time.sleep(0.08)
    assert run(store.get("k")) is not None, "should still be live at 80 ms"

    # Read again at ~160 ms from original write but only ~80 ms from last touch
    time.sleep(0.08)
    assert run(store.get("k")) is not None, (
        "touch on the first get should have extended TTL — still live at 160 ms total"
    )

    # Wait past TTL from last touch
    time.sleep(0.18)
    assert run(store.get("k")) is None, "expired after TTL from last touch"
