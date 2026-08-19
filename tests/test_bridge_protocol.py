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


@pytest.mark.asyncio
async def test_spec_management_round_trip(bridge: BridgeProcess) -> None:
    await bridge.call("new_build", {"name": "pob-mcp test"})
    baseline = await bridge.call("list_specs")
    assert len(baseline["specs"]) == 1

    search = await bridge.call("search_tree", {"type": "Notable", "limit": 400})
    node = next(n for n in search["nodes"] if n["pathCost"] is not None and not n["allocated"])
    await bridge.call("alloc_node", {"id": node["id"]})
    allocated_count = (await bridge.call("list_specs"))["specs"][0]["allocatedNodeCount"]
    # list_specs' count must agree with get_tree_state's count for the active spec.
    assert allocated_count == (await bridge.call("get_tree_state"))["allocatedNodeCount"]

    created = await bridge.call("create_spec", {"title": "Alt Tree"})
    assert created["ok"] is True
    after_create = await bridge.call("list_specs")
    assert len(after_create["specs"]) == 2
    new_spec = after_create["specs"][created["index"] - 1]
    # 1, not 0: the automatic class-start node is always allocated, same as a fresh new_build.
    assert new_spec["allocatedNodeCount"] == 1, "a newly created spec must start with no extra nodes allocated"
    assert new_spec["active"] is True, "create_spec activates by default"

    await bridge.call("select_spec", {"index": 1})
    assert (await bridge.call("list_specs"))["specs"][0]["active"] is True

    copied = await bridge.call("copy_spec", {"title": "Copy"})
    assert len((await bridge.call("list_specs"))["specs"]) == 3
    await bridge.call("rename_spec", {"index": copied["index"], "title": "Renamed Copy"})
    renamed = (await bridge.call("list_specs"))["specs"][copied["index"] - 1]
    assert renamed["title"] == "Renamed Copy"
    assert renamed["allocatedNodeCount"] == allocated_count, "a copy must carry over the source's allocation"

    await bridge.call("delete_spec", {"index": copied["index"]})
    remaining = (await bridge.call("list_specs"))["specs"]
    assert len(remaining) == 2

    while len(remaining) > 1:
        await bridge.call("delete_spec", {"index": remaining[0]["index"]})
        remaining = (await bridge.call("list_specs"))["specs"]
    with pytest.raises(BridgeError):
        # a build always needs at least one spec
        await bridge.call("delete_spec", {"index": remaining[0]["index"]})


@pytest.mark.asyncio
async def test_item_set_management_round_trip(bridge: BridgeProcess) -> None:
    await bridge.call("new_build", {"name": "pob-mcp test"})
    baseline = await bridge.call("list_item_sets")
    assert len(baseline["itemSets"]) == 1
    default_id = baseline["itemSets"][0]["id"]

    await bridge.call(
        "equip_item_raw",
        {
            "text": (
                "The Anvil\nBloodstone Amulet\nVariant: Current\nImplicits: 1\n"
                "{tags:life}+(30-40) to maximum Life\n"
            )
        },
    )
    life_with_amulet = (await bridge.call("get_stats", {"fields": ["Life"]}))["stats"]["Life"]

    created = await bridge.call("create_item_set", {"title": "Alt Gear"})
    assert created["ok"] is True
    life_on_new_set = (await bridge.call("get_stats", {"fields": ["Life"]}))["stats"]["Life"]
    assert life_on_new_set < life_with_amulet, "a newly created item set must start empty"

    await bridge.call("select_item_set", {"id": default_id})
    life_after_switch_back = (await bridge.call("get_stats", {"fields": ["Life"]}))["stats"]["Life"]
    assert life_after_switch_back == life_with_amulet, "switching back must restore the equipped amulet"

    copied = await bridge.call("copy_item_set", {"title": "Backup"})
    assert len((await bridge.call("list_item_sets"))["itemSets"]) == 3
    await bridge.call("rename_item_set", {"id": copied["id"], "title": "Renamed Backup"})
    renamed = next(s for s in (await bridge.call("list_item_sets"))["itemSets"] if s["id"] == copied["id"])
    assert renamed["title"] == "Renamed Backup"

    await bridge.call("delete_item_set", {"id": created["id"]})
    remaining_ids = {s["id"] for s in (await bridge.call("list_item_sets"))["itemSets"]}
    assert created["id"] not in remaining_ids
    assert len(remaining_ids) == 2
