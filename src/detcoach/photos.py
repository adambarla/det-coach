"""Fetch freely licensed photos from Wikimedia Commons, with the attribution a round needs."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
UA = "det-coach/0.1 (https://github.com/adambarla/det-coach)"
WIDTH = 1280
FREE = ("CC0", "Public domain", "CC BY", "CC BY-SA")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _plain(html: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", html or "")).strip()


def fetch(title: str, dest: Path, name: str | None = None) -> tuple[str, dict]:
    """Download `title` (e.g. "File:Bicycle repair.jpg") at 1280 px into dest/.

    Returns the saved file name and the photo entry for round.json.
    Raises ValueError for files without a free license.
    """
    if not title.startswith("File:"):
        title = "File:" + title
    q = urllib.parse.urlencode(
        {
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": WIDTH,
            "format": "json",
        }
    )
    page = next(iter(json.loads(_get(f"{API}?{q}"))["query"]["pages"].values()))
    if "imageinfo" not in page:
        raise FileNotFoundError(title)
    info = page["imageinfo"][0]
    meta = info.get("extmetadata", {})
    license_ = _plain(meta.get("LicenseShortName", {}).get("value", ""))
    if not license_.startswith(FREE):
        raise ValueError(f"{title} has license '{license_}', which is not free to reuse")
    ext = Path(urllib.parse.urlparse(info.get("thumburl") or info["url"]).path).suffix.lower()
    name = name or re.sub(r"[^a-z0-9]+", "-", Path(title[5:]).stem.lower()).strip("-")[:48]
    if not name.endswith(ext):
        name += ext
    dest.mkdir(parents=True, exist_ok=True)
    (dest / name).write_bytes(_get(info.get("thumburl") or info["url"]))
    return name, {
        "title": title[5:],
        "author": _plain(meta.get("Artist", {}).get("value", "")) or "unknown",
        "license": license_,
        "source": info["descriptionurl"],
    }
