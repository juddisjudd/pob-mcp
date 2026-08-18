"""The optimize_build MCP tool."""

from __future__ import annotations

from mcp.server.mcpserver import Context, MCPServer

from ..app_context import get_manager
from .engine import optimize


def _filter_stats(stats: dict, fields: list[str] | None) -> dict:
    """Trim a stats dict to just `fields` (matching get_stats' own filtering), or return it
    unchanged if no filter was requested."""
    if not fields:
        return stats
    return {key: stats.get(key) for key in fields}


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    async def optimize_build(
        ctx: Context,
        goal: str = "balanced",
        scope: list[str] | None = None,
        max_iterations: int = 15,
        dps_weight: float = 0.5,
        defence_weight: float = 0.5,
        tree_search_radius: int = 8,
        apply: bool = True,
        fields: list[str] | None = None,
    ) -> dict:
        """Iteratively improve the currently loaded build toward a goal, using PoB's real
        calculation engine to evaluate every candidate change (this is a heuristic greedy local
        search, not a guaranteed global optimum -- see stoppedReason/appliedMoves in the result).

        goal: "damage" (maximize DPS), "defence" (maximize effective survivability), or "balanced"
            (weighted combination of both, normalized against this build's own baseline so DPS and
            EHP scales don't dominate each other -- see dps_weight/defence_weight).
        scope: which move types to search, any of "tree", "gems", "items" (default: all three).
            - tree: allocate additional reachable passive nodes. Additive only -- never deallocates
              or respecs existing nodes.
            - gems: swap a support gem (never the group's first/main gem) for another PoB considers
              valid, at the same level/quality.
            - items: swap an equipped item for another unique from PoB's bundled local item database
              that fits the same slot. No live trade/market pricing, no rare-item crafting search.
              Jewel sockets aren't reliably matched by this and are effectively skipped -- use
              list_uniques_for_slot + equip_item_raw manually to try specific jewels.
            Configuration options (buffs, enemy stats, etc.) are never searched automatically, so
            the optimizer can't inflate its score by assuming an unrealistic scenario -- call
            set_config yourself first if you want to optimize for a specific one.
        max_iterations: cap on greedy hill-climbing steps; stops earlier once no candidate move
            improves the score.
        tree_search_radius: only consider tree nodes within this many passive points of the current
            allocation, purely as a search-cost bound -- not an enforcement of the build's actual
            available point budget. Review the total point cost of any suggested allocation before
            committing to it in-game.
        apply: if true (default), the best build found is left loaded when this call returns. If
            false, the original build is restored before returning and this becomes a "preview" run
            -- read the report, then decide whether to actually apply it.
        fields: restrict baselineStats/finalStats in the response to these stat keys (same idea as
            get_stats). Omit to get every scalar stat PoB computed -- useful for a first look, but
            it's a large response (300+ fields); once you know which ones matter for this build,
            pass them explicitly. This only trims the report -- scoring during the search always
            considers the full stat set regardless of this filter.
        """
        manager = get_manager(ctx)
        bridge = await manager.primary()
        effective_scope = scope or ["tree", "gems", "items"]

        pre_snapshot = await bridge.snapshot()
        result = await optimize(
            bridge,
            goal,
            effective_scope,
            max_iterations=max_iterations,
            dps_weight=dps_weight,
            defence_weight=defence_weight,
            tree_search_radius=tree_search_radius,
        )
        if not apply:
            await bridge.restore(pre_snapshot)

        baseline_stats = _filter_stats(result.baseline_stats, fields)
        final_stats = _filter_stats(result.final_stats, fields)

        return {
            "goal": result.goal,
            "scope": effective_scope,
            "applied": apply,
            "iterationsRun": result.iterations_run,
            "stoppedReason": result.stopped_reason,
            "appliedMoves": result.applied_moves,
            "baselineScore": result.baseline_score,
            "finalScore": result.final_score,
            "baselineStats": baseline_stats,
            "finalStats": final_stats,
        }
