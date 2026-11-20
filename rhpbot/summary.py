"""Short ECM summary from the cover of a DRHP, UDRHP, or RHP."""

from __future__ import annotations

import re

_SPACE = re.compile(r"\s+")
_BANK = re.compile(r"([A-Z][A-Za-z0-9&.,'’\-()][A-Za-z0-9&.,'’\-() ]{2,80}?(?:Limited|LLP))")
# A size cell is either "Not applicable" or "up to N equity shares ... aggregating up to ₹X".
# The rupee amount may still be the unset placeholder [●].
_SIZE = re.compile(
    r"(?:(?:fresh issue(?:\s+and\s+offer\s+for\s+sale)?|offer\s+for\s+sale)\s+of\s+)?"
    r"up\s+to\s+(?P<shares>\[(?:●|•)\]|[\d,]+)\s+equity\s+shares"
    r"(?:\s+of\s+face\s+value\s+of\s+₹\s*(?P<face>[\d,.]+)\s+each)?"
    r"\s+aggregating\s+up\s+to\s+₹\s*(?P<amount>\[(?:●|•)\]|[\d,]+(?:\.\d+)?)\s*"
    r"(?P<unit>lakhs?|crores?|millions?)"
    r"|(?P<na>\bnot\s+applicable\b)"
    r"|aggregating\s+up\s+to\s+₹\s*(?P<only>[\d,]+(?:\.\d+)?)\s*(?P<only_unit>lakhs?|crores?|millions?)",
    re.I,
)


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
    if not promoter:
        promoter = re.search(r"PROMOTERS OF OUR COMPANY ARE\s+(.+?)\s+DETAILS OF", cover, re.I)
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
        lines.append("Business: " + fields["business"])
    if "objects" in fields:
        lines.append("")
        lines.append("Objects: " + fields["objects"])
    lines.append("")
    lines.append(page)
    if full and full != page:
        lines.append(full)
    return "\n".join(lines).strip()


def _issue(cover: str) -> dict[str, str]:
    """Fresh, offer for sale, then total, in the order of the cover table.

    "Not applicable" belongs to whichever column it sits in. A cell whose price
    is still [●] keeps the share count instead of being dropped.
    """
    upper = cover.upper()
    begin = -1
    for marker in ("DETAILS OF THE OFFER TO THE PUBLIC", "DETAILS OF THE ISSUE TO THE PUBLIC", "DETAILS OF ISSUE", "DETAILS OF THE OFFER", "FRESH ISSUE"):
        begin = upper.find(marker)
        if begin >= 0:
            break
    if begin < 0:
        return {}
    finish = upper.find("RISKS IN RELATION", begin)
    if finish < 0:
        finish = begin + 1600
    block = cover[begin:finish]
    # A PDF sometimes splits a word or a number across a line, so "applicable" and "456" come back broken.
    block = re.sub(r"(?<=\d)\s+(?=\d)", "", block)
    block = re.sub(r"not\s+applicabl\s*e", "not applicable", block, flags=re.I)
    data = block
    for marker in ("ELIGIBILITY AND RESERVATION", "ELIGIBILITY"):
        at = data.upper().find(marker)
        if at >= 0:
            data = data[at + len(marker):]
            break
    stop = re.search(r"\bThe (?:Issue|Offer) is being made\b", data, re.I)
    if stop:
        data = data[:stop.start()]
    labels = ("fresh", "ofs", "total")
    fields: dict[str, str] = {}
    for label, match in zip(labels, _SIZE.finditer(data)):
        fields[label] = _size_text(match)
    return fields


def _size_text(match: re.Match) -> str:
    if match.group("na"):
        return "none"
    amount = match.group("amount") or match.group("only")
    unit = match.group("unit") or match.group("only_unit") or ""
    if amount and not amount.startswith("["):
        return _crore(amount, unit)
    shares = match.group("shares") or "[●]"
    share_text = "up to [●] equity shares" if shares.startswith("[") else f"up to {shares} equity shares"
    parts = [share_text]
    face = match.group("face")
    if face:
        parts.append(f"of face value ₹{face} each")
    unit_word = "million"
    if unit.lower().startswith("lakh"):
        unit_word = "lakhs"
    elif unit.lower().startswith("crore"):
        unit_word = "crore"
    parts.append(f"aggregating up to ₹[●] {unit_word}")
    if len(parts) == 3:
        return f"{parts[0]} {parts[1]}, {parts[2]}"
    return f"{parts[0]}, {parts[1]}"


def _bank_name(raw: str) -> str:
    name = re.sub(r"^.*(?:TELEPHONE|LOGO|CONTACT PERSON)\s+", "", raw, flags=re.I)
    name = re.sub(r"^(?:.*\b)?(?:and\s+)?e-\s*mail\s+", "", name, flags=re.I)
    name = _SPACE.sub(" ", name).strip(" .,-")
    low = name.lower()
    if not name or low in {"private limited", "limited", "llp"} or any(
        skip in low for skip in ("telephone", "logo", "bse limited", "national stock", "stock exchange")
    ):
        return ""
    return name


def _business(text: str) -> str:
    """The opening business description, through the last sentence before the next subsection."""
    anchor = text.upper().find("BUSINESS OVERVIEW")
    if anchor < 0:
        return ""
    region = text[anchor:anchor + 4000]
    start = re.search(r"\b(?:We are|Our Company is|The Company is)\b", region)
    if not start:
        return ""
    body = region[start.start():]
    stop = re.search(r"\s+[b-e][\.\)]\s+|\s+Set out below\b|\s+The following table\b", body, re.I)
    if stop:
        body = body[:stop.start()]
    body = re.sub(r"([A-Za-z])\d{1,2}\b", r"\1", body)
    body = _SPACE.sub(" ", body).strip()
    if len(body) > 1800:
        body = body[:1800].rsplit(". ", 1)[0] + "."
    return body


def _crore(raw: str, unit: str) -> str:
    value = float(raw.replace(",", ""))
    low = unit.lower()
    if low.startswith("lakh"):
        value /= 100
    elif low.startswith("million"):
        value /= 10
    if value >= 100:
        return f"₹{value:,.0f} crore"
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"₹{text} crore"


def _bankers(text: str) -> list[str]:
    # The cover mentions the managers once in a risk paragraph and again in the actual table, just before the registrar.
    upper = text.upper()
    finish = len(text)
    for end in ("REGISTRAR TO THE ISSUE", "REGISTRAR TO THE OFFER"):
        at = upper.find(end)
        if 0 <= at < finish:
            finish = at
    begin = upper.rfind("BOOK RUNNING LEAD", 0, finish)
    block = "" if begin < 0 else text[begin:finish]
    found = []
    for part in re.split(r"E-?mail", block, flags=re.I):
        names = _BANK.findall(part)
        if not names:
            continue
        name = _bank_name(names[-1])
        if name and name not in found:
            found.append(name)
    return found[:8]


def _sellers(text: str) -> list[str]:
    found = []
    patterns = (
        r"([A-Z][A-Za-z0-9&.,'’\- ]{2,70}?)\s+\((?:the\s+)?[\"“]?Selling Shareholder",
        r"((?:[A-Z][A-Za-z0-9&.'’\-]*\s+){1,8}?(?:Limited|Ltd\.?|LLP))\s+(?:Promoter\s+)?Selling Shareholder",
    )
    for pattern in patterns:
        for name in re.findall(pattern, text):
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
