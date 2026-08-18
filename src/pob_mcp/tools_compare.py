"""Build comparison: diffs two builds side by side using two disposable
scratch bridge processes, so the user's active session build is untouched."""

from __future__ import annotations

from mcp.server.mcpserver import Context, MCPServer

from .app_context import get_manager
from .importers import load_build as _load_build_impl


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    async def compare_builds(
        ctx: Context, source_a: str, source_b: str, fields: list[str] | None = None
    ) -> dict:
        """Compare two builds (each may be a PoB code, a supported site URL, a local .xml path, or
        raw XML) side by side, without touching the build currently loaded in this session.

        Returns each build's character summary plus a diff of every stat that differs between them
        (numeric stats include a `delta` = B - A). Pass `fields` to restrict the comparison to
        specific stat keys.
        """
        manager = get_manager(ctx)
        bridge_a = await manager.spawn_scratch()
        bridge_b = await manager.spawn_scratch()
        try:
            await _load_build_impl(bridge_a, source_a)
            await _load_build_impl(bridge_b, source_b)
            params = {"fields": fields} if fields else None
            stats_a = (await bridge_a.call("get_stats", params))["stats"]
            stats_b = (await bridge_b.call("get_stats", params))["stats"]
            character_a = await bridge_a.call("get_character")
            character_b = await bridge_b.call("get_character")

            diff: dict[str, dict] = {}
            for key in sorted(set(stats_a) | set(stats_b)):
                va, vb = stats_a.get(key), stats_b.get(key)
                if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                    if va != vb:
                        diff[key] = {"a": va, "b": vb, "delta": vb - va}
                elif va != vb:
                    diff[key] = {"a": va, "b": vb}

            return {"characterA": character_a, "characterB": character_b, "diff": diff}
        finally:
            await manager.release_scratch(bridge_a)
            await manager.release_scratch(bridge_b)
