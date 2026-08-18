"""Move-generator tests using a scripted fake bridge (no real luajit/PoB
process needed) -- verifies filtering/exclusion logic and that each move's
apply() calls the RPC methods it's supposed to."""

from __future__ import annotations

from typing import Any, Callable

import pytest

from pob_mcp.optimizer.moves import generate_gem_moves, generate_item_moves, generate_tree_moves


class ScriptedBridge:
    def __init__(self, responses: dict[str, Any]):
        self._responses = responses
        self.calls: list[tuple[str, dict]] = []

    async def call(self, method: str, params: dict | None = None, timeout: float = 30.0) -> Any:
        self.calls.append((method, params or {}))
        response = self._responses.get(method)
        if response is None:
            raise AssertionError(f"unscripted call to {method!r}")
        if isinstance(response, Callable):
            return response(params or {})
        return response


@pytest.mark.asyncio
async def test_generate_tree_moves_filters_by_radius_and_allocation() -> None:
    bridge = ScriptedBridge(
        {
            "search_tree": lambda params: {
                "nodes": [
                    {"id": 1, "name": "Far Notable", "allocated": False, "pathCost": 20},
                    {"id": 2, "name": "Near Notable", "allocated": False, "pathCost": 2},
                    {"id": 3, "name": "Allocated Notable", "allocated": True, "pathCost": 0},
                    {"id": 4, "name": "Unreachable Notable", "allocated": False, "pathCost": None},
                ]
            },
            "alloc_node": {"ok": True},
        }
    )
    moves = await generate_tree_moves(bridge, search_radius=5, limit=40)
    labels = [m.label for m in moves]
    assert any("Near Notable" in label for label in labels)
    assert not any("Far Notable" in label for label in labels)
    assert not any("Allocated Notable" in label for label in labels)
    assert not any("Unreachable Notable" in label for label in labels)

    await moves[0].apply(bridge)
    assert bridge.calls[-1][0] == "alloc_node"
    assert bridge.calls[-1][1]["id"] == 2


@pytest.mark.asyncio
async def test_generate_gem_moves_skips_main_gem_and_self_swap() -> None:
    bridge = ScriptedBridge(
        {
            "get_skills": {
                "socketGroups": [
                    {
                        "index": 1,
                        "enabled": True,
                        "gems": [
                            {"index": 1, "gemId": "Fireball", "level": 20, "quality": 0},
                            {"index": 2, "gemId": "SupportA", "level": 20, "quality": 0},
                        ],
                    }
                ]
            },
            "list_valid_supports": {
                "supports": [
                    {"gemId": "SupportA", "name": "Support A"},
                    {"gemId": "SupportB", "name": "Support B"},
                ]
            },
            "remove_gem": {"ok": True},
            "add_gem": {"ok": True, "gemIndex": 2},
        }
    )
    moves = await generate_gem_moves(bridge)
    assert moves, "expected at least one candidate gem swap"
    assert all("gem #2" in m.label for m in moves), "must never touch the group's first/main gem"
    assert any("Support B" in m.label for m in moves)
    assert not any("Support A" in m.label for m in moves), "must not offer swapping a gem for itself"

    await moves[0].apply(bridge)
    methods_called = [c[0] for c in bridge.calls[-2:]]
    assert methods_called == ["remove_gem", "add_gem"]


@pytest.mark.asyncio
async def test_generate_item_moves_skips_currently_equipped() -> None:
    bridge = ScriptedBridge(
        {
            "list_slots": {"slots": [{"slot": "Amulet", "itemId": 5, "itemName": "The Anvil"}]},
            "list_uniques_for_slot": {
                "items": [
                    {"name": "The Anvil", "raw": "raw-anvil"},
                    {"name": "Other Amulet", "raw": "raw-other"},
                ],
                "total": 2,
            },
            "equip_item_raw": {"ok": True},
        }
    )
    moves = await generate_item_moves(bridge)
    assert len(moves) == 1
    assert "Other Amulet" in moves[0].label

    await moves[0].apply(bridge)
    assert bridge.calls[-1][0] == "equip_item_raw"
    assert bridge.calls[-1][1] == {"text": "raw-other", "slot": "Amulet"}
