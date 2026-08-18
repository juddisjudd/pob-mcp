"""Locate a Path of Building - PoE2 installation and a LuaJIT interpreter.

Two modes:

* **dev checkout mode**: point ``POB_MCP_SOURCE_DIR`` at a PathOfBuilding-PoE2
  git checkout (its root, or its ``src`` directory directly). Lua source lives
  under ``src/``; the native runtime (LuaJIT DLLs, zlib, bundled Lua
  libraries) lives in a sibling ``runtime/`` directory.
* **release mode**: point ``POB_MCP_INSTALL_DIR`` at an installed release's
  root directory. Installed releases flatten everything -- ``Launch.lua``,
  ``Modules/``, ``zlib1.dll``, ``lua-utf8.dll``, the bundled ``lua/``
  libraries -- into that one directory; there's no ``src/``/``runtime/`` split.

What matters downstream is the resolved ``src_dir`` (becomes the bridge
subprocess's working directory, since ``Launch.lua`` resolves paths relative
to CWD) and ``runtime_dir`` (wherever the native DLLs and bundled Lua
libraries actually live -- not always ``src_dir``'s sibling; see
``_resolve_runtime_dir``).
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path


class PobNotFoundError(RuntimeError):
    pass


class LuaJitNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class PobInstall:
    src_dir: Path
    runtime_dir: Path
    mode: str  # "dev" or "release"


def _looks_like_src_dir(path: Path) -> bool:
    return (path / "Launch.lua").is_file() and (path / "Modules").is_dir()


def _resolve_runtime_dir(src_dir: Path) -> Path:
    """Where zlib1.dll / lua-utf8.dll / the bundled lua/*.lua libraries live for
    a given src_dir -- src_dir itself for a flattened release install, a
    sibling `runtime/` for a git checkout."""
    if (src_dir / "zlib1.dll").is_file() or (src_dir / "lua-utf8.dll").is_file():
        return src_dir
    return src_dir.parent / "runtime"


def _common_install_roots() -> list[Path]:
    names = ("Path of Building Community (PoE2)", "Path of Building-PoE2", "Path of Building (PoE2)")
    system = platform.system()
    candidates: list[Path] = []
    if system == "Windows":
        for env_var in ("APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
            base = os.environ.get(env_var)
            if base:
                for name in names:
                    candidates.append(Path(base) / name)
                    candidates.append(Path(base) / "Programs" / name)
    elif system == "Darwin":
        for name in names:
            candidates.append(Path.home() / "Applications" / name)
    else:
        for name in names:
            candidates.append(Path.home() / ".local" / "share" / name)
            candidates.append(Path("/opt") / name)
    return candidates


def locate_pob(
    source_dir: str | os.PathLike[str] | None = None,
    install_dir: str | os.PathLike[str] | None = None,
) -> PobInstall:
    """Resolve a usable ``src_dir`` from explicit args/env vars, or auto-detect.

    An explicitly-passed argument always wins over any environment variable --
    a caller who passed ``install_dir=`` meant that, regardless of what
    ``POB_MCP_SOURCE_DIR`` happens to be set to in the ambient environment.
    Only when *neither* argument is passed do the env vars apply, in which
    case: ``POB_MCP_SOURCE_DIR`` > ``POB_MCP_INSTALL_DIR`` > common release
    install locations.
    """
    if source_dir is None and install_dir is None:
        source_dir = os.environ.get("POB_MCP_SOURCE_DIR")
        install_dir = os.environ.get("POB_MCP_INSTALL_DIR")

    if source_dir:
        p = Path(source_dir).expanduser().resolve()
        candidate = p if _looks_like_src_dir(p) else p / "src"
        if _looks_like_src_dir(candidate):
            return PobInstall(src_dir=candidate, runtime_dir=_resolve_runtime_dir(candidate), mode="dev")
        raise PobNotFoundError(
            f"POB_MCP_SOURCE_DIR={p} does not look like a PathOfBuilding-PoE2 checkout "
            "(expected a 'Launch.lua' and 'Modules/' directory, either directly or under 'src/')."
        )

    if install_dir:
        p = Path(install_dir).expanduser().resolve()
        # Try the flattened release layout first, then the split one in case some
        # platform/portable build still uses it.
        for candidate in (p, p / "src"):
            if _looks_like_src_dir(candidate):
                return PobInstall(src_dir=candidate, runtime_dir=_resolve_runtime_dir(candidate), mode="release")
        raise PobNotFoundError(
            f"POB_MCP_INSTALL_DIR={p} does not look like a Path of Building - PoE2 install "
            "(expected a 'Launch.lua' directly under it, or under 'src/')."
        )

    for root in _common_install_roots():
        for candidate in (root, root / "src"):
            if _looks_like_src_dir(candidate):
                return PobInstall(src_dir=candidate, runtime_dir=_resolve_runtime_dir(candidate), mode="release")

    raise PobNotFoundError(
        "Could not find a Path of Building - PoE2 installation. Set POB_MCP_SOURCE_DIR to a "
        "PathOfBuilding-PoE2 git checkout, or POB_MCP_INSTALL_DIR to an installed release's root "
        "directory (see the README for both modes)."
    )


def locate_builds_dir(pob: PobInstall, explicit: str | os.PathLike[str] | None = None) -> Path | None:
    """Best-effort resolution of the user's PoB Builds folder, for listing local builds.

    Priority: explicit arg > POB_MCP_BUILDS_DIR env > portable-install convention
    (`<src_dir>/Builds` or `<src_dir>/../Builds`) > the typical per-OS user-data
    location. Returns None -- not an error -- if nothing is found, since this is
    inherently a guess without reading PoB's own settings.
    """
    candidate = explicit or os.environ.get("POB_MCP_BUILDS_DIR")
    if candidate:
        p = Path(candidate).expanduser().resolve()
        return p if p.is_dir() else None

    for portable in (pob.src_dir / "Builds", pob.src_dir.parent / "Builds"):
        if portable.is_dir():
            return portable

    system = platform.system()
    guesses: list[Path] = []
    if system == "Windows":
        for name in ("Path of Building (PoE2)", "Path of Building"):
            guesses.append(Path.home() / "Documents" / name / "Builds")
    elif system == "Darwin":
        for name in ("Path of Building (PoE2)", "Path of Building"):
            guesses.append(Path.home() / "Library" / "Application Support" / name / "Builds")
    else:
        for name in ("Path of Building (PoE2)", "Path of Building"):
            guesses.append(Path.home() / ".local" / "share" / name / "Builds")
    for g in guesses:
        if g.is_dir():
            return g
    return None


def locate_luajit(explicit: str | os.PathLike[str] | None = None) -> str:
    """Resolve a LuaJIT interpreter. PoB's own bundled runtime is a DLL used by
    its GUI host, not a standalone CLI, so a system LuaJIT (5.1-compatible)
    must be installed separately."""
    candidate = explicit or os.environ.get("POB_MCP_LUAJIT")
    if candidate:
        resolved = shutil.which(str(candidate)) or (str(candidate) if Path(candidate).is_file() else None)
        if resolved:
            return resolved
        raise LuaJitNotFoundError(f"POB_MCP_LUAJIT={candidate} was not found or is not executable.")

    for name in ("luajit", "luajit-2.1", "luajit.exe"):
        found = shutil.which(name)
        if found:
            return found

    raise LuaJitNotFoundError(
        "Could not find a 'luajit' executable on PATH. Install LuaJIT (5.1-compatible) and either "
        "add it to PATH or set POB_MCP_LUAJIT to its full path. This is separate from PoB's own "
        "bundled runtime, which only ships a DLL for its GUI host, not a CLI interpreter."
    )
