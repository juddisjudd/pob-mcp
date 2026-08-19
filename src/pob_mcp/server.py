"""pob-mcp server entrypoint: builds the MCPServer, wires up the PoB bridge
lifecycle, and registers every tool module."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer

from .app_context import AppContext
from .bridge import BridgeManager
from .locate import locate_luajit, locate_pob

logging.basicConfig(
    level=os.environ.get("POB_MCP_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("pob_mcp.server")


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    pob = locate_pob()
    luajit = locate_luajit()
    logger.info("using Path of Building (%s mode) at %s", pob.mode, pob.src_dir)
    logger.info("using luajit at %s", luajit)
    manager = BridgeManager(pob, luajit)
    try:
        yield AppContext(manager=manager)
    finally:
        await manager.close()


mcp = MCPServer(
    name="pob-mcp",
    title="Path of Building - PoE2",
    instructions=(
        "Load, inspect, modify, and optimize Path of Exile 2 builds using Path of Building's real "
        "calculation engine (not a reimplementation). Start with load_build, passing a PoB export "
        "code, a pobb.in/Maxroll/poe.ninja/poe2db.tw/Pastebin.com/Rentry.co link, or a local .xml "
        "build file path. Then use get_stats/get_character/get_tree_state/get_items/get_skills/"
        "get_config/sanity_check to inspect it, search_tree/node_info to explore the passive tree, "
        "alloc_node/dealloc_node/select_class/equip_item_raw/unequip_item/set_gem/add_gem/"
        "remove_gem/set_main_skill/set_config to change it, list_specs/list_item_sets (and "
        "select/create/copy/rename/delete for each) to manage a build's alternate passive tree "
        "specs and gear sets, compare_builds to diff two builds, export_build to get XML or a "
        "shareable code back out, and optimize_build to run a goal-directed (damage/defence/"
        "balanced) search over the tree, support gems, and local unique items."
    ),
    lifespan=app_lifespan,
)

# Imported after `mcp` is constructed: each module's register() attaches its
# tools to this instance.
from . import (  # noqa: E402
    tools_compare,
    tools_export,
    tools_inspect,
    tools_local,
    tools_mutate,
    tools_specs,
    tools_treesearch,
)
from .optimizer import tool as optimizer_tool  # noqa: E402

tools_inspect.register(mcp)
tools_mutate.register(mcp)
tools_treesearch.register(mcp)
tools_specs.register(mcp)
tools_compare.register(mcp)
tools_export.register(mcp)
tools_local.register(mcp)
optimizer_tool.register(mcp)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
