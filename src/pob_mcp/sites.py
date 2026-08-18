"""Fetches PoB build codes from the same sites PoB's own Import tab supports.

Mirrors `buildSites.websiteList` in the PathOfBuilding-PoE2 repo
(src/Modules/BuildSiteTools.lua) rather than re-deriving these patterns,
since the desktop app's own in-process networking (lcurl) isn't available
headless. Each site's `downloadURL` endpoint returns the raw PoB build code
(the same base64-ish text you'd paste into PoB's Import box) -- not XML --
so callers should feed the result to the bridge's `load_build_code` RPC,
which reuses PoB's own base64+inflate decode path for byte-identical
behaviour to the desktop app.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

USER_AGENT = "pob-mcp (+https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2)"


@dataclass(frozen=True)
class BuildSite:
    id: str
    label: str
    match: re.Pattern[str]
    extract: re.Pattern[str]
    download_template: str

    def download_url(self, url: str) -> str:
        m = self.extract.search(url)
        if not m:
            raise ValueError(f"could not extract a build id from {url!r} for site {self.label}")
        return self.download_template.format(id=m.group(1))


SITES: list[BuildSite] = [
    BuildSite(
        id="Maxroll",
        label="Maxroll",
        match=re.compile(r"^https://maxroll\.gg/poe2/pob/.*"),
        extract=re.compile(r"maxroll\.gg/poe2/pob/(.+?)\s*$"),
        download_template="https://maxroll.gg/poe2/api/pob/{id}",
    ),
    BuildSite(
        id="POBBin",
        label="pobb.in",
        match=re.compile(r"^https://pobb\.in/.+"),
        extract=re.compile(r"pobb\.in/(.+?)\s*$"),
        download_template="https://pobb.in/pob/{id}",
    ),
    BuildSite(
        id="PoeNinja",
        label="poe.ninja",
        match=re.compile(r"^https://poe2?\.ninja/?p?o?e?2?/pob/.+"),
        extract=re.compile(r"poe2?\.ninja/?p?o?e?2?/pob/(.+?)\s*$"),
        download_template="https://poe.ninja/poe2/pob/raw/{id}",
    ),
    BuildSite(
        id="PoE2DB",
        label="poe2db.tw",
        match=re.compile(r"^https://poe2db\.tw/pob/.+"),
        extract=re.compile(r"poe2db\.tw/pob/(.+?)\s*$"),
        download_template="https://poe2db.tw/pob/{id}/raw",
    ),
    BuildSite(
        id="pastebin",
        label="Pastebin.com",
        match=re.compile(r"^https://pastebin\.com/\w+"),
        extract=re.compile(r"pastebin\.com/(\w+)\s*$"),
        download_template="https://pastebin.com/raw/{id}",
    ),
    BuildSite(
        id="pastebinProxy",
        label="PastebinP.com",
        match=re.compile(r"^https://pastebinp\.com/\w+"),
        extract=re.compile(r"pastebinp\.com/(\w+)\s*$"),
        download_template="https://pastebinp.com/raw/{id}",
    ),
    BuildSite(
        id="rentry",
        label="Rentry.co",
        match=re.compile(r"rentry\.co/\w+"),
        extract=re.compile(r"rentry\.co/(\w+)\s*$"),
        download_template="https://rentry.co/paste/{id}/raw",
    ),
]


def find_site(url: str) -> BuildSite | None:
    for site in SITES:
        if site.match.search(url):
            return site
    return None


def is_supported_url(text: str) -> bool:
    return find_site(text) is not None


async def fetch_code_for_url(url: str, timeout: float = 20.0) -> str:
    """Fetch raw build-code text for a supported site URL (paste/share link)."""
    site = find_site(url)
    if site is None:
        supported = ", ".join(s.label for s in SITES)
        raise ValueError(f"unrecognised build-site URL: {url!r} (supported sites: {supported})")
    download_url = site.download_url(url)
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        response = await client.get(download_url)
        response.raise_for_status()
        return response.text.strip()
