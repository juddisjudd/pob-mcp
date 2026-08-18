"""End-to-end bridge tests against a real `luajit` + Path of Building install.

Skipped automatically if either can't be located (see locate.py) -- e.g. in
CI or a dev sandbox without LuaJIT installed. Point POB_MCP_SOURCE_DIR (or
POB_MCP_INSTALL_DIR) and, if needed, POB_MCP_LUAJIT at a real setup to run
this for real; see the README's "Verification" section.
"""

from __future__ import annotations

import pytest

from pob_mcp.bridge import BridgeError, BridgeProcess
from pob_mcp.locate import LuaJitNotFoundError, PobNotFoundError, locate_luajit, locate_pob

try:
    _pob = locate_pob()
    _luajit = locate_luajit()
    _skip_reason = None
except (PobNotFoundError, LuaJitNotFoundError) as exc:
    _pob = None
    _luajit = None
    _skip_reason = str(exc)

pytestmark = pytest.mark.skipif(_skip_reason is not None, reason=_skip_reason or "")


@pytest.fixture
async def bridge():
    proc = BridgeProcess(_pob, _luajit)
    await proc.start()
    yield proc
    await proc.stop()


@pytest.mark.asyncio
async def test_ping(bridge: BridgeProcess) -> None:
    result = await bridge.call("ping")
    assert result["ok"] is True
    # The BUILD mode object is pre-initialized with a usable default build even before
    # load_build_xml/new_build is called explicitly -- buildLoaded reflects that, not
    # whether *we* have loaded something yet.
    assert isinstance(result["buildLoaded"], bool)


@pytest.mark.asyncio
async def test_new_build_and_inspect(bridge: BridgeProcess) -> None:
    await bridge.call("new_build", {"name": "pob-mcp test"})

    character = await bridge.call("get_character")
    assert character["classId"] is not None
    assert isinstance(character["level"], (int, float))

    stats = (await bridge.call("get_stats"))["stats"]
    assert "Life" in stats

    tree = await bridge.call("get_tree_state")
    assert tree["allocatedNodeCount"] >= 1  # the class start node is always allocated


@pytest.mark.asyncio
async def test_tree_search_and_alloc_dealloc_round_trip(bridge: BridgeProcess) -> None:
    await bridge.call("new_build", {"name": "pob-mcp test"})
    search = await bridge.call("search_tree", {"type": "Notable", "limit": 400})
    # Some Notables (ascendancy-locked ones for a different ascendancy) have no path
    # from the current allocation -- pick one that's actually reachable.
    reachable = [n for n in search["nodes"] if n["pathCost"] is not None and not n["allocated"]]
    assert reachable, "expected at least one reachable, unallocated Notable"

    node = reachable[0]
    node_id = node["id"]
    before = (await bridge.call("get_tree_state"))["allocatedNodeCount"]

    alloc_result = await bridge.call("alloc_node", {"id": node_id})
    assert alloc_result["ok"] is True
    after_alloc = (await bridge.call("get_tree_state"))["allocatedNodeCount"]
    assert after_alloc > before

    info = await bridge.call("node_info", {"id": node_id})
    assert info["allocated"] is True

    await bridge.call("dealloc_node", {"id": node_id})
    after_dealloc = (await bridge.call("get_tree_state"))["allocatedNodeCount"]
    # dealloc_node removes only the target node, not the intermediate path nodes PoB
    # auto-allocated to reach it -- so this is one less than after_alloc, not `before`.
    assert after_dealloc == after_alloc - 1
    info_after = await bridge.call("node_info", {"id": node_id})
    assert info_after["allocated"] is False


@pytest.mark.asyncio
async def test_save_and_reload_round_trip(bridge: BridgeProcess) -> None:
    await bridge.call("new_build", {"name": "pob-mcp test"})
    xml = (await bridge.call("save_build_xml"))["xml"]
    assert "<PathOfBuilding" in xml

    await bridge.call("load_build_xml", {"xml": xml, "name": "reloaded"})
    stats = (await bridge.call("get_stats"))["stats"]
    assert "Life" in stats


@pytest.mark.asyncio
async def test_list_config_options_is_nonempty(bridge: BridgeProcess) -> None:
    result = await bridge.call("list_config_options")
    assert len(result["options"]) > 10
    assert all(opt["var"] for opt in result["options"]), "every option must carry a settable var id"


@pytest.mark.asyncio
async def test_select_class_rolls_back_cleanly_on_invalid_id(bridge: BridgeProcess) -> None:
    await bridge.call("new_build", {"name": "pob-mcp test"})
    before = await bridge.call("get_character")

    with pytest.raises(BridgeError):
        await bridge.call("select_class", {"classId": 0})  # 0 is not a valid class id

    after = await bridge.call("get_character")
    assert after == before, "a failed select_class must not leave the build partially changed"


@pytest.mark.asyncio
async def test_select_class_with_valid_id_changes_class(bridge: BridgeProcess) -> None:
    await bridge.call("new_build", {"name": "pob-mcp test"})
    classes = (await bridge.call("list_classes"))["classes"]
    before = await bridge.call("get_character")
    other = next(c for c in classes if c["id"] != before["classId"])

    await bridge.call("select_class", {"classId": other["id"]})
    after = await bridge.call("get_character")
    assert after["classId"] == other["id"]
    assert after["className"] == other["name"]


@pytest.mark.asyncio
async def test_add_gem_with_real_gem_id_produces_dps(bridge: BridgeProcess) -> None:
    await bridge.call("new_build", {"name": "pob-mcp test"})
    matches = (await bridge.call("list_gems", {"query": "fireball", "onlySupports": False}))["gems"]
    fireball = next(g for g in matches if g["name"] == "Fireball")

    await bridge.call("add_socket_group", {"label": "main"})
    await bridge.call("add_gem", {"groupIndex": 1, "gemId": fireball["gemId"], "level": 20, "quality": 0})

    stats = (await bridge.call("get_stats", {"fields": ["TotalDPS"]}))["stats"]
    assert stats["TotalDPS"] > 0


@pytest.mark.asyncio
async def test_large_response_does_not_break_the_bridge(bridge: BridgeProcess) -> None:
    """Regression test: search_tree with a large limit produces a response well over
    asyncio's default 64KB readline() limit -- must not be misreported as a process crash."""
    await bridge.call("new_build", {"name": "pob-mcp test"})
    result = await bridge.call("search_tree", {"limit": 2000})
    assert len(result["nodes"]) > 1000
    # the bridge must still be alive and responsive afterwards
    assert (await bridge.call("ping"))["ok"] is True


@pytest.mark.asyncio
async def test_sanity_check_returns_a_list(bridge: BridgeProcess) -> None:
    await bridge.call("new_build", {"name": "pob-mcp test"})
    result = await bridge.call("sanity_check")
    assert isinstance(result["warnings"], list)
