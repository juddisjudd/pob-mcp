"""Shared lifespan context type, split out from server.py to avoid a circular
import between server.py (which builds the MCPServer + lifespan) and the
tools_*.py modules (which need the same AppContext type to reach the bridge)."""

from __future__ import annotations

from dataclasses import dataclass

from mcp.server.mcpserver import Context

from .bridge import BridgeManager


@dataclass
class AppContext:
    manager: BridgeManager


def get_manager(ctx: Context) -> BridgeManager:
    return ctx.request_context.lifespan_context.manager
