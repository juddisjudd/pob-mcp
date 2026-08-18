"""Mutation tools: passive tree allocation, items, gems, and configuration.
Every tool here recalculates the build (via PoB's own buildFlag/OnFrame
recalculation path) before returning, so the response always reflects
up-to-date state -- call get_stats afterwards to see the resulting numbers."""

from __future__ import annotations

from mcp.server.mcpserver import Context, MCPServer

from .app_context import get_manager


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    async def node_path_cost(ctx: Context, node_id: int) -> dict:
        """Get the passive-point cost to allocate a given tree node from the current tree state
        (the length of PoB's own computed shortest path from the current allocation), without
        actually allocating it."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call("node_path_cost", {"id": node_id})

    @mcp.tool()
    async def alloc_node(ctx: Context, node_id: int) -> dict:
        """Allocate a passive tree node (and the shortest path to it from the current allocation,
        exactly as PoB's own tree UI would), then recalculate."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("alloc_node", {"id": node_id})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def dealloc_node(ctx: Context, node_id: int) -> dict:
        """Deallocate a passive tree node (and any nodes that depended on it for connectivity),
        then recalculate."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("dealloc_node", {"id": node_id})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def select_class(
        ctx: Context,
        class_id: int | None = None,
        ascend_class_id: int | None = None,
        secondary_ascend_class_id: int | None = None,
    ) -> dict:
        """Change the loaded build's class and/or ascendancy (PoE2 supports a secondary
        ascendancy). Omit any id to leave that selection unchanged. Changing class deallocates
        tree nodes incompatible with the new class. See list_classes for valid ids -- an
        invalid id raises an error and the build is left exactly as it was (no partial change)."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call(
            "select_class",
            {
                "classId": class_id,
                "ascendClassId": ascend_class_id,
                "secondaryAscendClassId": secondary_ascend_class_id,
            },
        )

    @mcp.tool()
    async def equip_item_raw(ctx: Context, item_text: str, slot: str | None = None) -> dict:
        """Parse raw in-game item text (the format you get from copying an item in-game or pasting
        one from PoB's item creation tools) and equip it. If `slot` is omitted, the first
        compatible empty/matching slot is used automatically."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("equip_item_raw", {"text": item_text, "slot": slot})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def unequip_item(ctx: Context, slot: str) -> dict:
        """Remove whatever item is in the given slot (see get_items for slot names)."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("unequip_item", {"slot": slot})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def add_socket_group(ctx: Context, label: str | None = None, slot: str | None = None) -> dict:
        """Create a new, empty skill/socket group -- use add_gem afterwards to put gems in it. A
        brand new build (from new_build) starts with zero socket groups. If this is the build's
        first socket group, it automatically becomes the main skill."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("add_socket_group", {"label": label, "slot": slot})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def set_main_skill(ctx: Context, group_index: int) -> dict:
        """Set which skill/socket group (1-based index, see get_skills) is used as the main skill
        for DPS calculations."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("set_main_skill", {"index": group_index})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def set_gem(
        ctx: Context,
        group_index: int,
        gem_index: int,
        level: int | None = None,
        quality: int | None = None,
        enabled: bool | None = None,
    ) -> dict:
        """Change an existing gem's level, quality, and/or enabled state (see get_skills for
        group_index/gem_index). Omit a field to leave it unchanged."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call(
            "set_gem",
            {"groupIndex": group_index, "gemIndex": gem_index, "level": level, "quality": quality, "enabled": enabled},
        )
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def add_gem(
        ctx: Context,
        group_index: int,
        gem_id: str | None = None,
        skill_id: str | None = None,
        level: int = 1,
        quality: int = 0,
    ) -> dict:
        """Add a gem to an existing socket group (see get_skills for group_index, add_socket_group
        to create one). Identify the gem by its gem_id (an internal path id, e.g.
        "Metadata/Items/Gems/SkillGemFireball" -- use list_gems to find it, don't guess), or by
        skill_id for skills without a distinct gem entry."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call(
            "add_gem",
            {"groupIndex": group_index, "gemId": gem_id, "skillId": skill_id, "level": level, "quality": quality},
        )
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def remove_gem(ctx: Context, group_index: int, gem_index: int) -> dict:
        """Remove a gem from a socket group (see get_skills for group_index/gem_index)."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("remove_gem", {"groupIndex": group_index, "gemIndex": gem_index})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def list_valid_supports(ctx: Context, group_index: int) -> dict:
        """List support gems PoB considers valid for a socket group's main active skill (see
        get_skills for group_index). Best-effort: if PoB can't resolve an active skill for the
        group yet (e.g. it has no active/main gem), returns an empty list with an explanatory note."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call("list_valid_supports", {"groupIndex": group_index})

    @mcp.tool()
    async def set_config(ctx: Context, var: str, value: bool | int | float | str | None) -> dict:
        """Set a configuration option (buffs, curses, enemy stats, map mods, and similar calculation
        assumptions). See list_config_options for valid `var` ids and their expected value types/
        ranges. Pass value=None to clear/reset an option to its default."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("set_config", {"var": var, "value": value})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}
