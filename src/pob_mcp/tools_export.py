"""Export the currently loaded build back to PoB XML or a shareable code."""

from __future__ import annotations

from pathlib import Path

from mcp.server.mcpserver import Context, MCPServer

from .app_context import get_manager


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    async def export_build(ctx: Context, format: str = "xml", to_file: str | None = None) -> dict:
        """Export the currently loaded build.

        format="xml" (default) returns full PoB build XML. format="code" returns a shareable PoB
        import code (the text you'd paste into PoB's Import tab or another pobb.in-style site);
        this requires zlib to be available to the bridge -- if it isn't, use format="xml" instead.
        If `to_file` is given, the result is also written to that local path.
        """
        manager = get_manager(ctx)
        bridge = await manager.primary()
        if format not in ("xml", "code"):
            raise ValueError("format must be 'xml' or 'code'")
        if format == "xml":
            content = (await bridge.call("save_build_xml"))["xml"]
        else:
            content = (await bridge.call("save_build_code"))["code"]
        if to_file:
            Path(to_file).expanduser().write_text(content, encoding="utf-8")
        return {"format": format, "content": content, "savedTo": to_file}
