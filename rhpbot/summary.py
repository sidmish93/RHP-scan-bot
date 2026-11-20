"""Short ECM summary from the cover of a DRHP, UDRHP, or RHP."""

from __future__ import annotations

import re

_SPACE = re.compile(r"\s+")
_AMOUNT = re.compile(r"₹\s*([0-9][0-9,]*(?:\.\d+)?)\s*(lakh|crore)s?", re.I)
_BANK = re.compile(r"([A-Z][A-Za-z0-9&.,'’\-][A-Za-z0-9&.,'’\- ]{2,70}?(?:Limited|LLP))")


def summarize(text: str) -> dict[str, str]:
    """Pull the fields that fit in a phone message. Missing fields are omitted."""
    collapsed = _SPACE.sub(" ", text or "").strip()
    cover = collapsed.split("IN THE NATURE OF", 1)[0][:6000]
    fields: dict[str, str] = {}

    fields.update(_issue(cover))

    pre = re.search(
        r"Pre-IPO Placement.{0,220}?aggregating up to\s+₹\s*([0-9][0-9,]*(?:\.\d+)?)\s*(lakh|crore)s?",
        collapsed,
        re.I,
    )
    if pre:
        fields["pre_ipo"] = "up to " + _crore(pre.group(1), pre.group(2))

    promoter = re.search(
        r"NAME OF OUR PROMOTERS?\s*[:\-]?\s*(.+?)\s+DETAILS OF (?:THE )?(?:ISSUE|OFFER)",
        cover,
        re.I,
    )
    if promoter:
        fields["promoter"] = _SPACE.sub(" ", promoter.group(1)).strip(" .:-")

    banks = _bankers(collapsed)
    if banks:
        fields["bankers"] = ", ".join(banks)

    sellers = _sellers(collapsed)
    if fields.get("ofs") == "none":
        fields["sellers"] = "none"
    elif sellers:
        fields["sellers"] = "; ".join(sellers)

    business = _business(collapsed)
    if business:
        fields["business"] = business

    objects = _objects(collapsed)
    if objects:
        fields["objects"] = " · ".join(objects)
    return fields


def render(kind: str, company: str, filed: str, fields: dict[str, str], page: str, full: str) -> str:
    lines = [f"{kind} · {company}"]
    if filed:
        lines.append(f"SEBI · {filed}")
    lines.append("")
    for label, key in (
        ("Fresh issue", "fresh"),
        ("Offer for sale", "ofs"),
        ("Total issue", "total"),
        ("Pre-IPO placement", "pre_ipo"),
    ):
        if key in fields:
            lines.append(f"{label}: {fields[key]}")
    if any(key in fields for key in ("promoter", "bankers", "sellers")):
        lines.append("")
    if "promoter" in fields:
        lines.append(f"Promoter: {fields['promoter']}")
    if "bankers" in fields:
        lines.append(f"Bankers: {fields['bankers']}")
    if "sellers" in fields:
        lines.append(f"Selling shareholders: {fields['sellers']}")
    if "business" in fields:
        lines.append("")
        lines.append(fields["business"])
    if "objects" in fields:
        lines.append("")
        lines.append("Objects: " + fields["objects"])
    lines.append("")
    lines.append(page)
    if full and full != page:
        lines.append(full)
    return "\n".join(lines).strip()


def _issue(cover: str) -> dict[str, str]:
    begin = cover.upper().find("DETAILS OF ISSUE")
    if begin < 0:
        begin = cover.upper().find("FRESH ISSUE")
    if begin < 0:
        return {}
    finish = cover.upper().find("RISKS IN RELATION", begin)
    if finish < 0:
        finish = begin + 1600
    block = cover[begin:finish]
    amounts = list(_AMOUNT.finditer(block))
    absent = re.search(r"not applicable", block, re.I)
    fields: dict[str, str] = {}
    if absent:
        before = [item for item in amounts if item.start() < absent.start()]
        after = [item for item in amounts if item.start() > absent.start()]
        if before:
            fields["fresh"] = _crore(before[0].group(1), before[0].group(2))
        fields["ofs"] = "none"
        if after:
            fields["total"] = _crore(after[0].group(1), after[0].group(2))
        return fields
    labels = ("fresh", "ofs", "total")
    for label, match in zip(labels, amounts):
        fields[label] = _crore(match.group(1), match.group(2))
    return fields


def _slice(text: str, start: str, end: str) -> str:
    begin = text.upper().find(start.upper())
    if begin < 0:
        return ""
    finish = text.upper().find(end.upper(), begin + len(start))
    if finish < 0:
        finish = begin + 500
    return text[begin:finish]


def _bank_name(raw: str) -> str:
    name = re.sub(r"^.*(?:TELEPHONE|LOGO|CONTACT PERSON)\s+", "", raw, flags=re.I)
    name = _SPACE.sub(" ", name).strip(" .,-")
    low = name.lower()
    if not name or any(skip in low for skip in ("telephone", "logo", "bse limited", "national stock", "stock exchange")):
        return ""
    return name


def _business(text: str) -> str:
    anchor = text.upper().find("BUSINESS OVERVIEW")
    region = text[anchor:anchor + 900] if anchor >= 0 else ""
    match = re.search(r"\bWe are\s+\S.{40,520}", region)
    if not match:
        return ""
    sentence = match.group(0).strip()
    if len(sentence) > 280:
        sentence = sentence[:277].rsplit(" ", 1)[0] + "..."
    return sentence


def _crore(raw: str, unit: str) -> str:
    value = float(raw.replace(",", ""))
    if unit.lower().startswith("lakh"):
        value /= 100
    if value >= 100:
        return f"₹{value:,.0f} crore"
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"₹{text} crore"


def _bankers(text: str) -> list[str]:
    block = _slice(text, "BOOK RUNNING LEAD MANAGERS", "REGISTRAR TO THE ISSUE")
    found = []
    for part in re.split(r"E-?mail", block, flags=re.I):
        names = _BANK.findall(part)
        if not names:
            continue
        name = _bank_name(names[-1])
        if name and name not in found:
            found.append(name)
    return found[:6]


def _sellers(text: str) -> list[str]:
    found = []
    for name in re.findall(
        r"([A-Z][A-Za-z0-9&.,'’\- ]{2,70}?)\s+\((?:the\s+)?[\"“]?Selling Shareholder",
        text,
    ):
        name = _SPACE.sub(" ", name).strip(" ,;")
        if name and name not in found:
            found.append(name)
    return found[:8]


def _objects(text: str) -> list[str]:
    start = text.upper().find("OBJECTS OF THE ISSUE")
    if start < 0:
        return []
    chunk = text[start:start + 1800]
    finish = chunk.upper().find("PRE AND POST")
    if finish > 0:
        chunk = chunk[:finish]
    objects = []
    for item in re.findall(r"\d+\.\s+(.*?)(?=\s+\d+\.\s+|\s+Total Net Proceeds|$)", chunk):
        item = re.sub(r"\s*\(?\d+\)?\s*$", "", item)
        item = re.sub(r"\s+[\d,.]+(?:\s*\[●\])?\s*$", "", item).strip(" .;")
        if len(item) < 12 or item.lower().startswith("general corporate") or item in objects:
            continue
        objects.append(item[:160])
        if len(objects) == 3:
            break
    return objects
