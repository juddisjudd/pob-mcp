"""Local PoB Builds-folder listing.

Not a true filesystem watcher -- for an LLM-driven session, re-calling this
tool on demand notices new/changed builds just as well as wiring up push
notifications would, at a fraction of the complexity.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.mcpserver import Context, MCPServer

from .app_context import get_manager
from .locate import locate_builds_dir


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    async def list_local_builds(ctx: Context, directory: str | None = None) -> dict:
        """List .xml build files in the user's local PoB Builds folder (or `directory`, if given).

        If no Builds folder can be found automatically, set the POB_MCP_BUILDS_DIR environment
        variable to point at one, or pass `directory` explicitly. Returned paths can be passed
        straight to load_build.
        """
        manager = get_manager(ctx)
        builds_dir = None
        if directory:
            builds_dir = Path(directory).expanduser()
        else:
            builds_dir = locate_builds_dir(manager.pob)

        if builds_dir is None or not builds_dir.is_dir():
            return {
                "directory": None,
                "builds": [],
                "note": (
                    "no Builds folder found automatically; set POB_MCP_BUILDS_DIR or pass "
                    "'directory' explicitly"
                ),
            }

        builds = []
        for path in sorted(builds_dir.rglob("*.xml")):
            try:
                stat = path.stat()
            except OSError:
                continue
            builds.append(
                {
                    "path": str(path),
                    "name": path.stem,
                    "sizeBytes": stat.st_size,
                    "modifiedAt": stat.st_mtime,
                }
            )
        return {"directory": str(builds_dir), "builds": builds}
