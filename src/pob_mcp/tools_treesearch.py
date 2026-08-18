"""Passive tree search, with class/ascendancy filtering."""

from __future__ import annotations

from mcp.server.mcpserver import Context, MCPServer

from .app_context import get_manager


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    async def search_tree(
        ctx: Context,
        query: str | None = None,
        node_type: str | None = None,
        ascendancy_name: str | None = None,
        main_tree_only: bool = False,
        limit: int = 200,
    ) -> dict:
        """Search the loaded build's passive tree (uses the tree version tied to the loaded build).

        `query`: case-insensitive substring matched against node names and stat text.
        `node_type`: filter to one of "Notable", "Keystone", "Mastery", "Normal", "ClassStart",
            "AscendClassStart", "Socket".
        `ascendancy_name`: filter to nodes belonging to a specific ascendancy (as shown in
            node_info's ascendancyName field).
        `main_tree_only`: if true (and ascendancy_name is not set), exclude all ascendancy nodes.
        `limit`: maximum nodes to return (default 200); result is marked `truncated` if hit.
        """
        manager = get_manager(ctx)
        bridge = await manager.primary()
        ascend_param: object
        if ascendancy_name:
            ascend_param = ascendancy_name
        elif main_tree_only:
            ascend_param = False
        else:
            ascend_param = None
        return await bridge.call(
            "search_tree",
            {"query": query, "type": node_type, "ascendancyName": ascend_param, "limit": limit},
        )
