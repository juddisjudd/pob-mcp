"""Unifies every supported way to point pob-mcp at a build: a pasted PoB
export code, a pobb.in/maxroll/poe.ninja/poe2db/pastebin/rentry link, a local
.xml file, or raw XML text -- resolving each down to a single bridge call.
"""

from __future__ import annotations

import re
from pathlib import Path

from .bridge import BridgeProcess
from .sites import fetch_code_for_url, is_supported_url

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_XML_RE = re.compile(r"^\s*<\?xml|^\s*<PathOfBuilding", re.IGNORECASE)


class ImportError_(ValueError):
    pass


async def load_build(bridge: BridgeProcess, source: str, name: str | None = None) -> dict:
    """Load a build into `bridge` from any supported source.

    `source` may be: raw XML text, a local filesystem path to a .xml build
    file, a supported build-site URL, or a raw pasted PoB export code.
    """
    source = source.strip()
    if not source:
        raise ImportError_("empty build source")

    if _XML_RE.search(source):
        return await bridge.call("load_build_xml", {"xml": source, "name": name or ""})

    maybe_path = Path(source)
    if maybe_path.is_file():
        if maybe_path.suffix.lower() != ".xml":
            raise ImportError_(f"expected a .xml build file, got: {maybe_path}")
        xml_text = maybe_path.read_text(encoding="utf-8")
        return await bridge.call("load_build_xml", {"xml": xml_text, "name": name or maybe_path.stem})

    if _URL_RE.search(source):
        if "poe.ninja" in source.lower() and "/pob/" not in source.lower():
            raise NotImplementedError(
                "importing a live poe.ninja *character* profile (as opposed to a poe.ninja pob-link) "
                "is not implemented yet -- it needs the official character API, which pob-mcp does not "
                "integrate with in this version. Export the character to a PoB code/link first."
            )
        if not is_supported_url(source):
            raise ImportError_(
                f"unsupported URL: {source!r}. Supported sites: pobb.in, Maxroll, poe.ninja (pob-link), "
                "poe2db.tw, Pastebin.com, PastebinP.com, Rentry.co. For anything else, download the build "
                "as a .xml file or copy its PoB export code instead."
            )
        code = await fetch_code_for_url(source)
        return await bridge.call("load_build_code", {"code": code, "name": name or ""})

    # Otherwise assume it's a raw pasted PoB export code.
    return await bridge.call("load_build_code", {"code": source, "name": name or ""})
