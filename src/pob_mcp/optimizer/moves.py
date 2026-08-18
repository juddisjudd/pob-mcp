"""Candidate move generators for the optimizer.

Each generator produces a bounded list of `Move`s -- a label plus an async
`apply(bridge)` that performs the change (and its own recalculation, via the
bridge's normal RPC methods). The engine is responsible for snapshotting
before trying a move and rolling back after scoring it, so generators don't
need to worry about undoing anything themselves, including partial failures
partway through a multi-step move (e.g. a gem swap that removes the old gem
successfully but fails to add the replacement).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..bridge import BridgeProcess

ApplyFn = Callable[[BridgeProcess], Awaitable[None]]


@dataclass
class Move:
    label: str
    kind: str
    apply: ApplyFn


async def generate_tree_moves(bridge: BridgeProcess, search_radius: int, limit: int = 40) -> list[Move]:
    """Additive-only: allocate one more reachable Notable/Keystone. Does not
    consider deallocating/respeccing existing nodes -- that combinatorial
    space is out of scope for this heuristic search."""
    moves: list[Move] = []
    for node_type in ("Notable", "Keystone"):
        search = await bridge.call("search_tree", {"type": node_type, "limit": 400})
        for node in search["nodes"]:
            if node["allocated"]:
                continue
            cost = node.get("pathCost")
            if cost is None or cost > search_radius:
                continue
            node_id = node["id"]
            label = f"Allocate '{node['name']}' (+{cost} pt{'s' if cost != 1 else ''})"

            async def apply(bridge: BridgeProcess, node_id: int = node_id) -> None:
                await bridge.call("alloc_node", {"id": node_id})

            moves.append(Move(label=label, kind="tree", apply=apply))
    moves.sort(key=lambda m: m.label)
    return moves[:limit]


async def generate_gem_moves(bridge: BridgeProcess, supports_per_group: int = 8) -> list[Move]:
    """Swap-only: replace an existing support gem with another PoB considers
    valid for the group's active skill, at the same level/quality. Skips each
    group's first gem (assumed to be the active skill itself)."""
    moves: list[Move] = []
    skills = await bridge.call("get_skills")
    for group in skills["socketGroups"]:
        if not group["enabled"]:
            continue
        group_index = group["index"]
        try:
            valid = await bridge.call("list_valid_supports", {"groupIndex": group_index})
        except Exception:
            continue
        candidates = valid.get("supports", [])[:supports_per_group]
        if not candidates:
            continue
        for gem in group["gems"][1:]:
            gem_index = gem["index"]
            level = gem.get("level") or 20
            quality = gem.get("quality") or 0
            current_gem_id = gem.get("gemId")
            for candidate in candidates:
                if candidate["gemId"] == current_gem_id:
                    continue

                async def apply(
                    bridge: BridgeProcess,
                    group_index: int = group_index,
                    gem_index: int = gem_index,
                    gem_id: str = candidate["gemId"],
                    level: int = level,
                    quality: int = quality,
                ) -> None:
                    await bridge.call("remove_gem", {"groupIndex": group_index, "gemIndex": gem_index})
                    await bridge.call(
                        "add_gem", {"groupIndex": group_index, "gemId": gem_id, "level": level, "quality": quality}
                    )

                moves.append(
                    Move(
                        label=f"Group {group_index}: swap gem #{gem_index} for '{candidate['name']}'",
                        kind="gem",
                        apply=apply,
                    )
                )
    return moves


async def generate_item_moves(bridge: BridgeProcess, candidates_per_slot: int = 12) -> list[Move]:
    """Swap-only: replace an equipped item with another unique from PoB's
    bundled local database that fits the same slot. No trade/market pricing,
    no rare-item crafting search. Jewel sockets are not meaningfully matched
    by this (their slot names don't line up with unique GetPrimarySlot()
    values), so in practice this only produces gear moves -- which is the
    intended, documented scope."""
    moves: list[Move] = []
    slots = (await bridge.call("list_slots"))["slots"]
    for slot in slots:
        slot_name = slot["slot"]
        current_name = slot.get("itemName")
        try:
            result = await bridge.call("list_uniques_for_slot", {"slot": slot_name, "limit": candidates_per_slot})
        except Exception:
            continue
        for candidate in result.get("items", []):
            if candidate["name"] == current_name:
                continue
            raw = candidate["raw"]
            name = candidate["name"]

            async def apply(bridge: BridgeProcess, slot_name: str = slot_name, raw: str = raw) -> None:
                await bridge.call("equip_item_raw", {"text": raw, "slot": slot_name})

            moves.append(Move(label=f"Equip '{name}' in {slot_name}", kind="item", apply=apply))
    return moves
