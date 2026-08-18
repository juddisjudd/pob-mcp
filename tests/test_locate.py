"""Regression coverage for the split (git checkout: src/ + sibling runtime/)
vs flattened (installed release: everything in one directory) layouts."""

from __future__ import annotations

from pathlib import Path

from pob_mcp.locate import PobNotFoundError, locate_pob


def _make_checkout_layout(root: Path) -> None:
    src = root / "src"
    src.mkdir()
    (src / "Launch.lua").write_text("")
    (src / "Modules").mkdir()
    runtime = root / "runtime"
    runtime.mkdir()
    (runtime / "zlib1.dll").write_text("")
    (runtime / "lua-utf8.dll").write_text("")
    lua_dir = runtime / "lua"
    lua_dir.mkdir()
    (lua_dir / "xml.lua").write_text("")


def _make_flattened_release_layout(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Launch.lua").write_text("")
    (root / "Modules").mkdir()
    (root / "zlib1.dll").write_text("")
    (root / "lua-utf8.dll").write_text("")
    lua_dir = root / "lua"
    lua_dir.mkdir()
    (lua_dir / "xml.lua").write_text("")


def test_dev_checkout_layout_keeps_src_and_runtime_separate(tmp_path: Path) -> None:
    _make_checkout_layout(tmp_path)
    pob = locate_pob(source_dir=str(tmp_path))
    assert pob.mode == "dev"
    assert pob.src_dir == tmp_path / "src"
    assert pob.runtime_dir == tmp_path / "runtime"


def test_release_install_layout_is_flattened(tmp_path: Path) -> None:
    install_root = tmp_path / "Path of Building Community (PoE2)"
    _make_flattened_release_layout(install_root)
    pob = locate_pob(install_dir=str(install_root))
    assert pob.mode == "release"
    # The defining, easy-to-regress-on behaviour: src_dir and runtime_dir must be
    # the *same* directory for a flattened install, not src_dir's sibling.
    assert pob.src_dir == install_root
    assert pob.runtime_dir == install_root


def test_release_install_dir_also_accepts_split_layout(tmp_path: Path) -> None:
    """Some future/alternate release packaging might still use a split
    src/runtime layout -- install_dir should keep working if so."""
    _make_checkout_layout(tmp_path)
    pob = locate_pob(install_dir=str(tmp_path))
    assert pob.mode == "release"
    assert pob.src_dir == tmp_path / "src"
    assert pob.runtime_dir == tmp_path / "runtime"


def test_missing_install_raises_clear_error(tmp_path: Path) -> None:
    empty = tmp_path / "not-a-pob-install"
    empty.mkdir()
    try:
        locate_pob(install_dir=str(empty))
        assert False, "expected PobNotFoundError"
    except PobNotFoundError as exc:
        assert "not-a-pob-install" in str(exc)
