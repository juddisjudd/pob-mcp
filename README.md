# pob-mcp

pob-mcp is an MCP server. It lets an LLM load, inspect, change, and improve
[Path of Exile 2](https://www.pathofexile.com/) builds. It uses the real
calculation engine from [Path of Building Community (PoE2
fork)](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2). It
does not reimplement that engine.

pob-mcp runs a real, headless copy of PoB (a Lua program) as a background
process. It talks to that process over a small JSON-RPC protocol. Every stat
you get back is a number PoB itself calculated.

## How it works

```
MCP client (Claude Desktop, Cursor, ...)
        |  MCP over stdio
        v
   pob-mcp (Python)  -- tools_*.py, optimizer/
        |  JSON-RPC over stdio
        v
   lua/pob_bridge.lua  (running under `luajit`)
        |  dofile()
        v
   Path of Building - PoE2's own Lua source (Launch.lua, Main.lua, ...)
```

`lua/pob_bridge.lua` is a fork of PoB's own `src/HeadlessWrapper.lua`, which
PoB uses for its test suite. pob-mcp does not depend on that file directly.
Installed copies of PoB leave `HeadlessWrapper.lua` out (see
`manifest.cfg`), so pob-mcp brings its own version instead. This means
pob-mcp works the same way against a git checkout of PathOfBuilding-PoE2 and
against an installed release build.

## Before you start

You need four things:

1. **[uv](https://docs.astral.sh/uv/)**. Use it to install and run pob-mcp.
2. **[LuaJIT](https://luajit.org/)**, a 5.1-compatible build. Put it on your
   `PATH` as `luajit`, or point to it with `POB_MCP_LUAJIT`. You need this
   separately from PoB itself: PoB's own runtime only ships
   `lua51.dll`/`SimpleGraphic.dll` for its graphical app. It does not ship a
   command-line interpreter you can run on its own.
   * Windows: install it with [Scoop](https://scoop.sh)
     (`scoop install luajit`), [Chocolatey](https://chocolatey.org)
     (`choco install luajit`), or a portable build.
   * macOS: `brew install luajit`.
   * Linux: `apt install luajit`, the equivalent for your distribution, or
     build it from source.
3. **A Path of Building - PoE2 install.** This can be a git checkout (this
   repo, or your own clone) or an installed release build. See "Point
   pob-mcp at a PoB install" below.
4. **zlib.** pob-mcp needs this to read and write build codes, and to
   calculate Timeless Jewel data. On Windows, you already have this: PoB
   bundles `zlib1.dll` (in `runtime/` for a checkout, or alongside
   everything else for an installed release). On Linux and macOS, install
   your system's `zlib`/`libz` package if you don't have it already (most
   systems do). If pob-mcp can't find zlib, everything still works except
   pasted or shared build *codes* and Timeless Jewel calculations. Load and
   export builds as `.xml` files instead.

## Point pob-mcp at a PoB install

pob-mcp needs to know where your Path of Building - PoE2 install keeps its
Lua source, because that's what the bridge process runs against. There are
two ways to point it there. Note that the two have different layouts on
disk — pob-mcp detects which one you're using automatically.

* **Dev checkout mode.** Set `POB_MCP_SOURCE_DIR` to a PathOfBuilding-PoE2
  git checkout — either its root folder, or its `src` folder directly. This
  layout keeps the Lua source under `src/`, and keeps the native runtime
  (LuaJIT DLLs, zlib, the bundled Lua libraries) in a separate `runtime/`
  folder next to it.
* **Release mode.** Set `POB_MCP_INSTALL_DIR` to the root folder of an
  installed release. On Windows, this is usually
  `%APPDATA%\Path of Building Community (PoE2)`. An installed release puts
  everything in one folder — `Launch.lua`, `Modules/`, `zlib1.dll`, the
  bundled `lua/` libraries — instead of splitting it up. (We checked this
  against a real install. We didn't just guess from the repo's packaging
  config.)

If you don't set either variable, pob-mcp checks a few common install
locations for your operating system, and gives you a clear error if it
can't find one. On Windows, this already finds a normal installer-installed
copy without any setup on your part.

## Install pob-mcp

```bash
git clone <this repo, or wherever you put pob-mcp> pob-mcp
cd pob-mcp
uv sync
```

## Run it on its own (for testing)

```bash
POB_MCP_SOURCE_DIR=/path/to/PathOfBuilding-PoE2 uv run pob-mcp
# or, against an installed release:
POB_MCP_INSTALL_DIR="C:\Users\you\AppData\Roaming\Path of Building Community (PoE2)" uv run pob-mcp
```

This starts the MCP server over stdio. You won't see much happen — MCP
servers talk to MCP clients, not directly to you. See "Check that it
works," below, for a way to try it out without a full client.

## Use it with Claude Desktop, Cursor, or another MCP client

Add an entry to your client's MCP server config. For Claude Desktop, this
is `claude_desktop_config.json`. For Cursor, it's `mcp.json`.

```json
{
  "mcpServers": {
    "pob-mcp": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/pob-mcp", "run", "pob-mcp"],
      "env": {
        "POB_MCP_SOURCE_DIR": "/absolute/path/to/PathOfBuilding-PoE2"
      }
    }
  }
}
```

For release mode, use `POB_MCP_INSTALL_DIR` instead. Point it to the root
folder of your installed release — on Windows, usually
`%APPDATA%\Path of Building Community (PoE2)`:

```json
{
  "mcpServers": {
    "pob-mcp": {
      "command": "uv",
      "args": ["--directory", "C:\\path\\to\\pob-mcp", "run", "pob-mcp"],
      "env": {
        "POB_MCP_INSTALL_DIR": "C:\\Users\\you\\AppData\\Roaming\\Path of Building Community (PoE2)"
      }
    }
  }
}
```

Restart your client after you edit its config. You don't need to close Path
of Building itself. pob-mcp only reads game data from the install folder.
It never writes to it, so it runs fine alongside the app.

### Environment variables

| Variable | What it does |
|---|---|
| `POB_MCP_SOURCE_DIR` | Path to a PathOfBuilding-PoE2 git checkout (its root folder or `src/`) |
| `POB_MCP_INSTALL_DIR` | Path to the root folder of an installed release |
| `POB_MCP_LUAJIT` | Path to a `luajit` executable, if it isn't on `PATH` |
| `POB_MCP_ZLIB_PATH` | Path or name to load zlib from, if pob-mcp can't find it on its own |
| `POB_MCP_BUILDS_DIR` | Path to your PoB Builds folder, for `list_local_builds` |
| `POB_MCP_LOG_LEVEL` | Log level for the Python side (default `INFO`); the bridge's own output is logged at `DEBUG` |

## What you can do with it

Once your client is connected, start with `load_build`. Then use the other
tools to inspect, change, and improve the build:

* **Load a build**: `load_build` (takes a PoB export code, a
  pobb.in/Maxroll/poe.ninja pob-link/poe2db.tw/Pastebin.com/Rentry.co link,
  a local `.xml` file path, or raw XML text), `new_build`,
  `list_local_builds`.
* **Inspect a build**: `get_stats`, `list_stat_keys`, `get_character`,
  `list_classes`, `get_tree_state`, `node_info`, `search_tree`, `get_items`,
  `get_skills`, `list_gems`, `get_config`, `list_config_options`,
  `sanity_check`.
* **Change a build**: `alloc_node`/`dealloc_node`, `node_path_cost`,
  `select_class`, `equip_item_raw`/`unequip_item`, `add_socket_group`,
  `set_main_skill`, `add_gem`/`remove_gem`/`set_gem`, `list_valid_supports`,
  `set_config`.

  A note on gems: each gem has an internal id, and that id is not the same
  as its display name. Fireball's id, for example, is
  `"Metadata/Items/Gems/SkillGemFireball"`. Use `list_gems` to look up the
  right id — don't guess it. A wrong guess doesn't raise an error. It just
  silently fails to resolve, so the gem does nothing. The same goes for
  classes: `select_class` takes an internal class id, not a simple
  0-based index. Use `list_classes` to find it.
* **Improve a build**: `optimize_build(goal="damage"|"defence"|"balanced", scope=[...])`
  runs a goal-directed search over the passive tree, support gems, and
  local unique items. It checks every candidate change against PoB's real
  engine. See its own description in your MCP client for the full details,
  including what it deliberately leaves alone.
* **Compare or export**: `compare_builds`, `export_build`.

Every tool that changes the build also returns its updated `stats`. You
don't need a separate `get_stats` call to see the effect of a change.

## What this doesn't do (on purpose)

These are choices, not bugs:

* **The optimizer never changes configuration options** (buffs, curses,
  enemy stats, map mods). If it could, it could raise its own score by
  assuming an unrealistic scenario. Call `set_config` yourself first if you
  want to optimize for one specific scenario.
* **Item and jewel search only uses PoB's local database.** The `items`
  scope of `optimize_build` tries items from PoB's own bundled unique
  database, for the same slot. It doesn't check trade-site prices, and it
  doesn't search rare-item crafting options.
* **The optimizer doesn't search jewels on its own.** Matching a jewel to
  the right socket isn't reliable enough yet. You can still try a specific
  jewel by hand: use `list_uniques_for_slot`, then `equip_item_raw`.
* **The optimizer is a greedy search, not a perfect solver.** It only adds
  tree nodes — it never removes or replaces existing ones — and it only
  swaps one gem or item at a time. It can get stuck on a good-but-not-best
  answer that a wider search might beat.
* **pob-mcp can't import a live poe.ninja character profile.** It can
  import a poe.ninja *pob-link* just like any other supported site, but a
  live character profile is different: it needs the official character
  API, and this version doesn't talk to that API yet. Export the character
  to a PoB code or link first, and use that instead.
* **pob-mcp doesn't watch your Builds folder for changes.** `list_local_builds`
  lists what's there when you call it. It doesn't push updates when
  something changes. For an LLM-driven session, calling the tool again is
  simpler, and works just as well.

## Check that it works

Automated tests (run with `uv run pytest`) come in two groups:

* Tests that don't touch PoB at all (`test_importers.py`,
  `test_optimizer_goals.py`, `test_optimizer_moves.py`, `test_locate.py`).
  These run anywhere — you don't need LuaJIT or a PoB install.
* `test_bridge_protocol.py` runs a real bridge process from start to
  finish: it starts a new build, searches the tree, allocates and
  deallocates nodes, saves and reloads, lists config options, and runs a
  sanity check. If it can't find `POB_MCP_SOURCE_DIR`, `POB_MCP_INSTALL_DIR`,
  or a `luajit` executable, it **skips itself and tells you why**. Set
  those environment variables to actually run it.

To try the bridge by hand, without a full MCP client:

```bash
cd /path/to/PathOfBuilding-PoE2/src
luajit /absolute/path/to/pob-mcp/lua/pob_bridge.lua
```

Then type (or pipe in) JSON-RPC requests, one per line:

```json
{"id": 1, "method": "new_build", "params": {}}
{"id": 2, "method": "get_stats", "params": {}}
```

Each one should print back a `{"id": ..., "result": {...}}` line.

## Where things live

```
pob-mcp/
  lua/
    json.lua          # self-contained JSON codec for the bridge protocol
    pob_bridge.lua     # the headless PoB bridge + JSON-RPC loop
  src/pob_mcp/
    server.py          # MCP server entrypoint, tool registration
    bridge.py           # subprocess + JSON-RPC client for pob_bridge.lua
    locate.py           # finds a PoB install + luajit
    sites.py            # pobb.in/Maxroll/poe.ninja/etc. URL -> build code
    importers.py         # unifies code/URL/file/XML into one load_build path
    tools_*.py            # MCP tool definitions, grouped by area
    optimizer/             # goal-directed build search
  tests/
```
