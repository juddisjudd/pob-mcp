"""Read-only build inspection tools: load, stats, character, tree, items,
skills, config, and sanity checks."""

from __future__ import annotations

from mcp.server.mcpserver import Context, MCPServer

from .app_context import get_manager
from .importers import load_build as _load_build_impl


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    async def load_build(ctx: Context, source: str, name: str | None = None) -> dict:
        """Load a build into the active session, replacing whatever is currently loaded.

        `source` may be: a PoB export code (the text you'd paste into PoB's Import tab),
        a pobb.in / Maxroll / poe.ninja (pob-link) / poe2db.tw / Pastebin.com / Rentry.co URL,
        a local path to a .xml build file, or raw PoB build XML text.
        """
        manager = get_manager(ctx)
        bridge = await manager.primary()
        await _load_build_impl(bridge, source, name)
        stats = await bridge.call("get_stats")
        character = await bridge.call("get_character")
        return {"loaded": True, "character": character, "stats": stats["stats"]}

    @mcp.tool()
    async def new_build(ctx: Context, name: str | None = None) -> dict:
        """Start a brand new, blank build in the active session (default class, no items/skills)."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call("new_build", {"name": name})

    @mcp.tool()
    async def get_stats(ctx: Context, fields: list[str] | None = None) -> dict:
        """Get calculated character stats (life, ES, mana, resistances, DPS, EHP, etc.) for the
        currently loaded build, computed by PoB's real calculation engine.

        Pass `fields` (a list of stat keys) to get just those; omit it to get every scalar stat
        PoB computed. Call list_stat_keys first if you don't know which keys are available --
        exact key names vary by build (e.g. which DPS/EHP fields exist depends on skill/defence setup).
        """
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("get_stats", {"fields": fields} if fields else None)
        return result["stats"]

    @mcp.tool()
    async def list_stat_keys(ctx: Context) -> list[str]:
        """List every scalar stat key available from get_stats for the currently loaded build."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("list_stat_keys")
        return result["keys"]

    @mcp.tool()
    async def get_character(ctx: Context) -> dict:
        """Get the loaded build's class, ascendancy, and level."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call("get_character")

    @mcp.tool()
    async def list_classes(ctx: Context) -> list[dict]:
        """List every class and its ascendancies (id + name), for use with select_class."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("list_classes")
        return result["classes"]

    @mcp.tool()
    async def get_tree_state(ctx: Context) -> dict:
        """Get the loaded build's allocated passive tree: class/ascendancy ids, total allocated
        node count, and the full list of allocated node ids. Use node_info to look up details for
        any specific node id."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call("get_tree_state")

    @mcp.tool()
    async def node_info(ctx: Context, node_id: int) -> dict:
        """Get details for one passive tree node: name, type (Notable/Keystone/Mastery/Normal/
        ClassStart/AscendClassStart/Socket), its stat text, whether it's currently allocated, and
        its current pathing cost (points needed to allocate it from the current tree state)."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call("node_info", {"id": node_id})

    @mcp.tool()
    async def get_items(ctx: Context) -> dict:
        """List every equipment/jewel slot on the loaded build and what item (if any) is in it."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call("list_slots")

    @mcp.tool()
    async def list_gems(
        ctx: Context, query: str | None = None, only_supports: bool | None = None, limit: int = 50
    ) -> dict:
        """Look up gem ids for use with add_gem. Gems are identified by an internal path id (e.g.
        "Metadata/Items/Gems/SkillGemFireball" for Fireball), not their display name -- use this
        tool to find the right id rather than guessing.

        `query`: case-insensitive substring matched against both the gem id and its display name.
        `only_supports`: True to list only support gems, False to list only active/skill gems,
            omit for both.
        `limit`: maximum gems to return; the result is marked `truncated` if more matched.
        """
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call("list_gems", {"query": query, "onlySupports": only_supports, "limit": limit})

    @mcp.tool()
    async def get_skills(ctx: Context) -> dict:
        """List the loaded build's skill/socket groups, each gem within them (name, level, quality,
        enabled), and which group is the main skill used for DPS calculations."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        return await bridge.call("get_skills")

    @mcp.tool()
    async def get_config(ctx: Context) -> dict:
        """Get the loaded build's current configuration option values (buffs, curses, enemy stats,
        map mods, and similar calculation assumptions)."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("get_config")
        return result["config"]

    @mcp.tool()
    async def list_config_options(ctx: Context) -> list[dict]:
        """List every configuration option PoB supports (id, label, type, and valid values for
        list-type options), for use with set_config."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("list_config_options")
        return result["options"]

    @mcp.tool()
    async def sanity_check(ctx: Context) -> list[str]:
        """Run defensive sanity checks on the loaded build (uncapped/negative resistances, very low
        life for the character's level, missing Chaos Inoculation coverage on a low-life-style build,
        etc.) and return a list of human-readable warnings. An empty list means no issues were found
        by these heuristics -- it is not a guarantee the build is fully sound."""
        manager = get_manager(ctx)
        bridge = await manager.primary()
        result = await bridge.call("sanity_check")
        return result["warnings"]
