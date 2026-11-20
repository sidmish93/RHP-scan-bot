"""New DRHP, UDRHP, and RHP filings from SEBI's public-issue lists.

SEBI is the filing record. Draft offer documents (DRHP and UDRHP) and red herring
documents filed with the ROC (RHP) are separate lists, and a plain request returns
them. The exchange zip is only a copy, and it can leave out a document SEBI has
already posted.
"""

from __future__ import annotations

import datetime
import re
import urllib.request
from dataclasses import dataclass

DRAFTS = "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&ssid=15&smid=10"
RHPS = "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&ssid=15&smid=11"

_ROW = re.compile(r"<tr[^>]*>\s*<td>\s*([^<]+?)\s*</td>\s*<td>(.*?)</td>", re.S | re.I)
_PDF = re.compile(r"https://www\.sebi\.gov\.in/[^\"'\s>]+\.pdf", re.I)
_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Filing:
    id: str
    kind: str
    company: str
    filed: str
    page: str
    abridged: str
    full: str


def filings() -> list[Filing]:
    found = []
    seen = set()
    for url in (DRAFTS, RHPS):
        for item in parse_listing(_get(url)):
            if item.id in seen:
                continue
            seen.add(item.id)
            found.append(item)
    return found


def parse_listing(html: str) -> list[Filing]:
    items = []
    for date, cell in _ROW.findall(html or ""):
        title = _title(cell)
        kind = kind_of(title)
        if not kind:
            continue
        page = _page(cell)
        if not page:
            continue
        abridged, full = _pdfs(cell)
        items.append(
            Filing(
                id=page,
                kind=kind,
                company=_company(title),
                filed=_filed(date),
                page=page,
                abridged=abridged,
                full=full,
            )
        )
    return items


def kind_of(title: str) -> str | None:
    low = _SPACE.sub(" ", (title or "").replace("_", " ")).lower()
    if re.search(r"(?<![a-z])(?:addendum|corrigendum|price band)\b", low):
        return None
    if "udrhp" in low or "updated draft red herring" in low:
        return "UDRHP"
    if "drhp" in low or "draft red herring" in low:
        return "DRHP"
    if re.search(r"(?<![a-z])rhp\b", low) or "red herring prospectus" in low:
        return "RHP"
    return None


def attach(filing: Filing, page_html: str) -> Filing:
    """The list often links only the abridged prospectus. The full file is on the page."""
    abridged, full = _pdfs(page_html)
    return Filing(
        filing.id,
        filing.kind,
        filing.company,
        filing.filed,
        filing.page,
        filing.abridged or abridged,
        filing.full or full,
    )


def _pdfs(html: str) -> tuple[str, str]:
    abridged = ""
    full = ""
    for url in _PDF.findall(html or ""):
        low = url.lower()
        if "commondocs" in low or low.endswith("_p.pdf"):
            abridged = abridged or url
        elif "attachdocs" in low or "file=" in (html or "").lower():
            full = full or url
    for url in re.findall(r"file=(https://www\.sebi\.gov\.in/[^\"'&\s]+\.pdf)", html or "", re.I):
        full = full or url
    return abridged, full


def _page(cell: str) -> str:
    match = re.search(r'href="(https://www\.sebi\.gov\.in/filings/[^"]+)"', cell, re.I)
    return match.group(1) if match else ""


def _company(title: str) -> str:
    parts = re.split(r"\s*[-–—_]\s*(?:U?DRHP|RHP)\b", title, maxsplit=1, flags=re.I)
    return parts[0].strip(" -_") or title.strip()


def _filed(raw: str) -> str:
    try:
        day = datetime.datetime.strptime(raw.strip(), "%b %d, %Y")
    except ValueError:
        return raw.strip()
    return day.strftime("%d %b %Y")


def _title(cell: str) -> str:
    match = re.search(r'title="(.*?)(?:"\s+class=|">)', cell or "", re.S)
    raw = match.group(1) if match else (cell or "")
    text = _text(raw)
    text = re.split(r"\s+(?:Draft\s+)?Abridged\b", text, maxsplit=1, flags=re.I)[0]
    return text.strip(" -\"'")


def _text(cell: str) -> str:
    return _SPACE.sub(" ", _TAGS.sub(" ", cell or "")).strip()


def _get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read().decode("utf-8", "replace")
