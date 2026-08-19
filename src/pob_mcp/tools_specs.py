"""Passive tree spec and item set management.

A PoB build can hold several named passive tree specs (alternate leveling/
endgame trees) and several named gear sets, and switch between them. Every
other tool (get_tree_state, alloc_node, get_items, equip_item_raw, ...)
already reads whichever one is currently active, so selecting a different
spec or item set here changes what the rest of the tools see -- no separate
"apply" step needed.
"""

from __future__ import annotations

from mcp.server.mcpserver import Context, MCPServer

from .app_context import get_manager


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    async def list_specs(ctx: Context) -> dict:
        """List the loaded build's passive tree specs (class, ascendancy, points used, which
        one is active). Use select_spec/create_spec/copy_spec/rename_spec/delete_spec to manage
        them."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call("list_specs")

    @mcp.tool()
    async def select_spec(ctx: Context, index: int) -> dict:
        """Switch the active passive tree spec (see list_specs for index). All other tree tools
        then operate on this spec."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("select_spec", {"index": index})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def create_spec(ctx: Context, title: str | None = None, activate: bool = True) -> dict:
        """Create a new, blank passive tree spec (same class/ascendancy as the current one, no
        nodes allocated). Set activate=False to create it without switching to it."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("create_spec", {"title": title, "activate": activate})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def copy_spec(
        ctx: Context, source_index: int | None = None, title: str | None = None, activate: bool = True
    ) -> dict:
        """Duplicate a passive tree spec (defaults to the currently active one). Set
        activate=False to create the copy without switching to it."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call(
            "copy_spec", {"sourceIndex": source_index, "title": title, "activate": activate}
        )
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def rename_spec(ctx: Context, index: int, title: str) -> dict:
        """Rename a passive tree spec (see list_specs for index)."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call("rename_spec", {"index": index, "title": title})

    @mcp.tool()
    async def delete_spec(ctx: Context, index: int) -> dict:
        """Delete a passive tree spec (see list_specs for index). Fails if it's the only one
        left -- a build always needs at least one."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("delete_spec", {"index": index})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def list_item_sets(ctx: Context) -> dict:
        """List the loaded build's gear sets (id, title, which one is active). Use
        select_item_set/create_item_set/copy_item_set/rename_item_set/delete_item_set to manage
        them."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call("list_item_sets")

    @mcp.tool()
    async def select_item_set(ctx: Context, id: int) -> dict:
        """Switch the active gear set (see list_item_sets for id). get_items/equip_item_raw/
        unequip_item then operate on this set."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("select_item_set", {"id": id})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def create_item_set(ctx: Context, title: str | None = None, activate: bool = True) -> dict:
        """Create a new, empty gear set. Set activate=False to create it without switching to
        it."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("create_item_set", {"title": title, "activate": activate})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def copy_item_set(
        ctx: Context, source_id: int | None = None, title: str | None = None, activate: bool = True
    ) -> dict:
        """Duplicate a gear set (defaults to the currently active one). Set activate=False to
        create the copy without switching to it."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call(
            "copy_item_set", {"sourceId": source_id, "title": title, "activate": activate}
        )
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}

    @mcp.tool()
    async def rename_item_set(ctx: Context, id: int, title: str) -> dict:
        """Rename a gear set (see list_item_sets for id)."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call("rename_item_set", {"id": id, "title": title})

    @mcp.tool()
    async def delete_item_set(ctx: Context, id: int) -> dict:
        """Delete a gear set (see list_item_sets for id). Fails if it's the only one left -- a
        build always needs at least one."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("delete_item_set", {"id": id})
        stats = await bridge.call("get_stats")
        return {**result, "stats": stats["stats"]}
