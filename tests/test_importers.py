"""Pure-logic tests for build-site URL matching and import source dispatch.
No network access and no bridge process required."""

from __future__ import annotations

import pytest

from pob_mcp import sites
from pob_mcp.importers import ImportError_, load_build


@pytest.mark.parametrize(
    ("url", "expected_download"),
    [
        ("https://pobb.in/AbC123-xyz", "https://pobb.in/pob/AbC123-xyz"),
        ("https://maxroll.gg/poe2/pob/some-build", "https://maxroll.gg/poe2/api/pob/some-build"),
        ("https://poe.ninja/poe2/pob/abc123", "https://poe.ninja/poe2/pob/raw/abc123"),
        ("https://poe2db.tw/pob/abc123", "https://poe2db.tw/pob/abc123/raw"),
        ("https://pastebin.com/AbCd1234", "https://pastebin.com/raw/AbCd1234"),
        ("https://pastebinp.com/AbCd1234", "https://pastebinp.com/raw/AbCd1234"),
        ("https://rentry.co/abc123", "https://rentry.co/paste/abc123/raw"),
    ],
)
def test_site_download_url(url: str, expected_download: str) -> None:
    site = sites.find_site(url)
    assert site is not None, f"no site matched {url!r}"
    assert site.download_url(url) == expected_download


def test_unrecognised_url_has_no_site() -> None:
    assert sites.find_site("https://example.com/not-a-build-site") is None
    assert not sites.is_supported_url("https://example.com/not-a-build-site")


class _FakeBridge:
    """Records calls instead of talking to a real Lua process."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        self.calls.append((method, params or {}))
        return {"ok": True}


@pytest.mark.asyncio
async def test_load_build_dispatches_raw_xml() -> None:
    bridge = _FakeBridge()
    await load_build(bridge, "<?xml version='1.0'?><PathOfBuilding></PathOfBuilding>")
    assert bridge.calls[0][0] == "load_build_xml"
    assert "xml" in bridge.calls[0][1]


@pytest.mark.asyncio
async def test_load_build_dispatches_local_xml_file(tmp_path) -> None:
    build_file = tmp_path / "MyBuild.xml"
    build_file.write_text("<PathOfBuilding></PathOfBuilding>", encoding="utf-8")
    bridge = _FakeBridge()
    await load_build(bridge, str(build_file))
    assert bridge.calls[0][0] == "load_build_xml"
    assert bridge.calls[0][1]["name"] == "MyBuild"


@pytest.mark.asyncio
async def test_load_build_dispatches_raw_code() -> None:
    bridge = _FakeBridge()
    await load_build(bridge, "eNpr8k1MzlbILC5JzStRAAAgjgT2")
    assert bridge.calls[0][0] == "load_build_code"
    assert bridge.calls[0][1]["code"].startswith("eNpr")


@pytest.mark.asyncio
async def test_load_build_rejects_unsupported_url() -> None:
    bridge = _FakeBridge()
    with pytest.raises(ImportError_):
        await load_build(bridge, "https://example.com/some-build")


@pytest.mark.asyncio
async def test_load_build_rejects_poe_ninja_character_url() -> None:
    bridge = _FakeBridge()
    with pytest.raises(NotImplementedError):
        await load_build(bridge, "https://poe.ninja/poe2/builds/character/SomeAccount/SomeChar")
