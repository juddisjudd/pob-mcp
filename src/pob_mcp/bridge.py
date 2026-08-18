"""Subprocess + JSON-RPC-over-stdio client for lua/pob_bridge.lua.

One BridgeProcess = one running `luajit pob_bridge.lua`, i.e. one live,
in-memory PoB build session. Calls are serialized with a lock: each RPC
mutates or reads shared Lua-side build state, and the accuracy-first design
goal is better served by simple, race-free sequencing than by pipelining.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from .locate import PobInstall

logger = logging.getLogger("pob_mcp.bridge")

BRIDGE_LUA_PATH = Path(__file__).resolve().parent.parent.parent / "lua" / "pob_bridge.lua"

DEFAULT_TIMEOUT = 30.0
# asyncio.StreamReader.readline() defaults to a 64KB limit, which a single JSON-RPC
# frame (search_tree, save_build_xml) can easily exceed. Left at the default, an
# oversized line raises inside the reader task and gets misreported as "bridge
# process exited" on every pending call, when the process is actually still alive.
STREAM_LIMIT = 32 * 1024 * 1024


class BridgeError(RuntimeError):
    """Raised for both transport failures and Lua-side RPC errors."""


class BridgeProcess:
    def __init__(self, pob: PobInstall, luajit_path: str, zlib_path: str | None = None):
        self._pob = pob
        self._luajit_path = luajit_path
        self._zlib_path = zlib_path
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._next_id = 0
        self._lock = asyncio.Lock()
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        if self.running:
            return
        if not BRIDGE_LUA_PATH.is_file():
            raise BridgeError(f"bridge script not found at {BRIDGE_LUA_PATH}")
        env = dict(os.environ)
        # PoB's bundled Lua libraries live outside LuaJIT's default search path, and
        # their location relative to src_dir depends on the install layout (see
        # locate.py's _resolve_runtime_dir) -- use runtime_dir as an absolute path
        # rather than a fixed relative guess that only holds for one layout.
        runtime_dir = self._pob.runtime_dir.as_posix()
        env["LUA_PATH"] = f"{runtime_dir}/lua/?.lua;{runtime_dir}/lua/?/init.lua;;"
        env["LUA_CPATH"] = f"{runtime_dir}/?.dll;{runtime_dir}/?.so;;"
        env["POB_MCP_ZLIB_PATH"] = self._zlib_path or f"{runtime_dir}/zlib1.dll"
        logger.info("starting bridge: %s %s (cwd=%s)", self._luajit_path, BRIDGE_LUA_PATH, self._pob.src_dir)
        self._proc = await asyncio.create_subprocess_exec(
            self._luajit_path,
            str(BRIDGE_LUA_PATH),
            cwd=str(self._pob.src_dir),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            limit=STREAM_LIMIT,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        failure: BaseException | None = None
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    message = json.loads(text)
                except json.JSONDecodeError:
                    logger.warning("bridge stdout was not valid JSON, ignoring: %.300s", text)
                    continue
                req_id = message.get("id")
                future = self._pending.pop(req_id, None)
                if future is None or future.done():
                    continue
                if "error" in message and message["error"] is not None:
                    future.set_exception(BridgeError(message["error"].get("message", "unknown bridge error")))
                else:
                    future.set_result(message.get("result"))
        except Exception as exc:  # noqa: BLE001 - deliberately broad: must not vanish silently
            # A reader-side failure (e.g. a response line longer than STREAM_LIMIT) is not
            # the same thing as the process dying, and must not be reported as such.
            failure = exc
            logger.exception("bridge reader loop failed (process may still be running)")
        finally:
            error_message = f"bridge reader failed: {failure}" if failure else "bridge process exited before responding"
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(BridgeError(error_message))
            self._pending.clear()

    async def _drain_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        try:
            while True:
                line = await self._proc.stderr.readline()
                if not line:
                    break
                logger.debug("[lua] %s", line.decode("utf-8", errors="replace").rstrip())
        except Exception:  # pragma: no cover - best-effort logging only
            pass

    async def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = DEFAULT_TIMEOUT) -> Any:
        async with self._lock:
            if not self.running:
                await self.start()
            assert self._proc is not None and self._proc.stdin is not None
            self._next_id += 1
            req_id = self._next_id
            loop = asyncio.get_running_loop()
            future: asyncio.Future[Any] = loop.create_future()
            self._pending[req_id] = future
            # Strip None-valued params so an omitted optional arg is a genuinely absent
            # Lua table key (params.x == nil), not the json.null sentinel -- the Lua
            # methods consistently use `~= nil` to mean "caller didn't pass this".
            clean_params = {k: v for k, v in (params or {}).items() if v is not None}
            frame = json.dumps({"id": req_id, "method": method, "params": clean_params}) + "\n"
            try:
                self._proc.stdin.write(frame.encode("utf-8"))
                await self._proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as exc:
                self._pending.pop(req_id, None)
                raise BridgeError(f"bridge process is not accepting input: {exc}") from exc
            try:
                return await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError as exc:
                self._pending.pop(req_id, None)
                raise BridgeError(f"timed out after {timeout}s waiting for '{method}'") from exc

    async def stop(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.stdin is not None:
                self._proc.stdin.close()
        except Exception:
            pass
        for task in (self._reader_task, self._stderr_task):
            if task is not None:
                task.cancel()
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            self._proc.kill()
            await self._proc.wait()
        self._proc = None

    async def snapshot(self) -> str:
        """Return the current build's full XML, for later restore()."""
        result = await self.call("save_build_xml")
        return result["xml"]

    async def restore(self, xml_snapshot: str) -> None:
        await self.call("load_build_xml", {"xml": xml_snapshot, "name": "snapshot-restore"})


class BridgeManager:
    """Owns the long-lived 'primary' session bridge and can spin up short-lived
    scratch bridges for operations that must not disturb the user's active
    session (compare_builds, the optimizer's isolated trial evaluation)."""

    def __init__(self, pob: PobInstall, luajit_path: str, zlib_path: str | None = None):
        self._pob = pob
        self._luajit_path = luajit_path
        self._zlib_path = zlib_path
        self._primary: BridgeProcess | None = None
        self._scratch: list[BridgeProcess] = []

    @property
    def pob(self) -> PobInstall:
        return self._pob

    async def primary(self) -> BridgeProcess:
        if self._primary is None:
            self._primary = BridgeProcess(self._pob, self._luajit_path, self._zlib_path)
            await self._primary.start()
        return self._primary

    async def spawn_scratch(self) -> BridgeProcess:
        proc = BridgeProcess(self._pob, self._luajit_path, self._zlib_path)
        await proc.start()
        self._scratch.append(proc)
        return proc

    async def release_scratch(self, proc: BridgeProcess) -> None:
        if proc in self._scratch:
            self._scratch.remove(proc)
        await proc.stop()

    async def close(self) -> None:
        if self._primary is not None:
            await self._primary.stop()
            self._primary = None
        for proc in list(self._scratch):
            await proc.stop()
        self._scratch.clear()
