"""Short ECM summary from the cover of a DRHP, UDRHP, or RHP."""

from __future__ import annotations

import re

_SPACE = re.compile(r"\s+")
_BANK = re.compile(
    r"([A-Z][A-Za-z0-9&.,'’\-()][A-Za-z0-9&.,'’\-() ]{2,80}?(?i:Limited|LLP))"
)
# A size cell is either "Not applicable" or "up to N equity shares ... aggregating up to ₹X".
# The rupee amount may still be the unset placeholder [●].
_SIZE = re.compile(
    r"(?:(?:fresh issue(?:\s+and\s+offer\s+for\s+sale)?|offer\s+for\s+sale)\s+of\s+)?"
    r"(?:up\s+to\s+)?(?P<shares>\[(?:●|•)\]|[\d,]+)\s+equity\s+shares"
    r"(?:\s+(?:of|bearing)\s+face\s+value\s+of\s+₹\s*(?P<face>[\d,.]+)\s+each)?"
    r".{0,180}?"
    r"aggregating(?:\s+up)?\s+to\s+₹\s*(?P<amount>\[(?:●|•)\]|[\d,]+(?:\.\d+)?)\s*"
    r"(?P<unit>lakhs?|crores?|millions?)"
    r"|(?P<na>\bnot\s+applicable\b)"
    r"|aggregating(?:\s+up)?\s+to\s+₹\s*(?P<only>[\d,]+(?:\.\d+)?)\s*(?P<only_unit>lakhs?|crores?|millions?)",
    re.I,
)


def summarize(text: str) -> dict[str, str]:
    """Pull the fields that fit in a phone message. Missing fields are omitted."""
    collapsed = _SPACE.sub(" ", text or "").strip()
    fields: dict[str, str] = {}
    # The issue table is found by its own heading, wherever the cover banner sits.
    fields.update(_issue(collapsed))

    pre = re.search(
        r"Pre-IPO Placement.{0,220}?aggregating up to\s+₹\s*([0-9][0-9,]*(?:\.\d+)?)\s*(lakh|crore)s?",
        collapsed,
        re.I,
    )
    if pre:
        fields["pre_ipo"] = "up to " + _crore(pre.group(1), pre.group(2))

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
    if any(key in fields for key in ("bankers", "sellers")):
        lines.append("")
    if "bankers" in fields:
        lines.append(f"Bankers: {fields['bankers']}")
    if "bankers" in fields and "sellers" in fields:
        lines.append("")
    if "sellers" in fields:
        lines.append(f"Selling shareholders: {fields['sellers']}")
    if "business" in fields:
        lines.append("")
        lines.append("Business: " + fields["business"])
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
    for marker in (
        "DETAILS OF THE OFFER TO THE PUBLIC",
        "DETAILS OF THE ISSUE TO THE PUBLIC",
        "DETAILS OF THE ISSUE TO PUBLIC",
        "DETAILS OF THE ISSUE OF THE EQUITY",
        "DETAILS OF THE ISSUE",
        "DETAILS OF ISSUE",
        "DETAILS OF THE OFFER",
        "FRESH ISSUE",
    ):
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
    name = re.sub(r"^.*\bbook running lead managers?\s+", "", name, flags=re.I)
    name = re.sub(r"^(?:contact)\s+", "", name, flags=re.I)
    name = re.sub(r"^(?:.*\b)?(?:and\s+)?e-\s*mail\s+", "", name, flags=re.I)
    name = re.sub(r"^(?:formerly\s+known\s+as\s+)+", "", name, flags=re.I)
    name = re.sub(r"^id\s+", "", name, flags=re.I)
    name = _SPACE.sub(" ", name).strip(" .,-")
    if name.isupper():
        name = name.title()
    low = name.lower()
    if not name or low in {"private limited", "limited", "llp"} or any(
        skip in low for skip in ("telephone", "logo", "bse limited", "national stock", "stock exchange")
    ):
        return ""
    return name


# The abridged prospectus schedule item, not a sentence that happens to say "we are".
_SECTION = re.compile(
    r"summary of (?:the )?primary business|(?<![A-Za-z])primary business(?=\s+[a-h][.)])",
    re.I,
)
# The next outline item. The period that closes the previous sentence stays in that sentence.
_OUTLINE = re.compile(
    r"\s+\(?[a-h]\)(?=\s+[A-Z])"
    r"|\s+[a-h][.)](?=\s+[A-Z])"
    r"|\s+(?:[1-9]|1[0-2])[.)](?=\s+[A-Z])"
    r"|(?:^|(?<! [a-h]\.\s)(?<=\.\s))business overview\b",
    re.I,
)
# The schedule label in front of the first sentence, for example
# "Business overview – products or services offered by our Company".
_LABEL = re.compile(
    r"^(?:our business model\s+)?"
    r"(?:business overview\b"
    r"(?:(?:\s*[–\-:/]\s*|\s+)"
    r"(?!(?:we|as per|according to)\b)"
    r"(?!(?<!by )(?:our company|the company)\b)"
    r"[A-Za-z/,&]+)*)?",
    re.I,
)


def has_business_section(text: str) -> bool:
    return _section_end(_SPACE.sub(" ", text or "")) >= 0


def _business(text: str) -> str:
    """The prose under the primary-business heading, through the next outline item.

    The paragraph may open with the company's name. When that heading is only a
    label, the description is the first lettered subsection. A later products
    table is the next outline item, so it is not part of the paragraph.
    """
    end = _section_end(text)
    if end < 0:
        return ""
    region = text[end:end + 4000]
    body = _business_body(region)
    body = re.sub(r"\s*For further (?:details|information), see\b.*$", "", body, flags=re.I)
    body = re.sub(r"([A-Za-z]{3,})\d{1,2}\b", r"\1", body)
    body = re.sub(r"\s+\.", ".", body)
    body = _SPACE.sub(" ", body).strip()
    stop = max(body.rfind("."), body.rfind("!"))
    if stop >= 24:
        body = body[:stop + 1]
    if len(body) < 25:
        return ""
    if len(body) > 1800:
        body = body[:1800].rsplit(". ", 1)[0] + "."
    return body


def _section_end(text: str) -> int:
    """Where the primary-business body starts. A contents entry is not the section."""
    for match in _SECTION.finditer(text or ""):
        after = text[match.end():match.end() + 200]
        if re.search(r"\.{3,}", after[:70]):
            continue
        if re.match(r"\s*\d{1,3}\b", after) and not re.search(r"[a-h][.)]\s+[A-Z]", after, re.I):
            continue
        return match.end()
    for match in re.finditer(r"\bbusiness overview\b", text or "", re.I):
        after = text[match.end():match.end() + 220]
        before = text[max(0, match.start() - 24):match.start()]
        if re.search(r"\.{3,}", after[:70]):
            continue
        if re.search(r"\b(?:see|on page)\b", before, re.I):
            continue
        if "." in after and re.search(r"\b(?:we|the company|our company)\b", after, re.I):
            return match.end()
    return -1


def _business_body(region: str) -> str:
    marks = list(_OUTLINE.finditer(region))
    if not marks:
        return _drop_title(region)
    intro = _drop_title(region[:marks[0].start()])
    if len(intro) >= 25 and "." in intro:
        return intro
    finish = marks[1].start() if len(marks) > 1 else len(region)
    return _drop_title(region[marks[0].end():finish])


def _drop_title(text: str) -> str:
    """Drop the subsection label in front of the first sentence."""
    return _LABEL.sub("", text.strip(), count=1).strip()


def _crore(raw: str, unit: str) -> str:
    value = float(raw.replace(",", ""))
    low = unit.lower()
    if low.startswith("lakh"):
        value /= 100
    elif low.startswith("million"):
        value /= 10
    if value >= 100 and abs(value - round(value)) < 0.05:
        return f"₹{value:,.0f} crore"
    if value >= 100:
        return f"₹{value:,.2f} crore"
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"₹{text} crore"


def _bankers(text: str) -> list[str]:
    """The cover names the managers in the table, and again in sentences that do not.

    The table is the last mention before the registrar that actually contains a firm.
    A parenthetical "formerly known as" is the previous name, not the firm.
    """
    upper = text.upper()
    finish = len(text)
    for end in ("REGISTRAR TO THE ISSUE", "REGISTRAR TO THE OFFER"):
        at = upper.find(end)
        if 0 <= at < finish:
            finish = at
    begin = finish
    while True:
        begin = upper.rfind("BOOK RUNNING LEAD", 0, begin)
        if begin < 0:
            return []
        found = _banker_names(text[begin:finish])
        if found:
            return found[:8]


def _banker_names(block: str) -> list[str]:
    found = []
    for part in re.split(r"E-?mail", block, flags=re.I):
        part = re.sub(r"\(\s*formerly\b.*?\)", "", part, flags=re.I)
        names = _BANK.findall(part)
        if not names:
            continue
        name = _bank_name(names[-1])
        if name and name not in found:
            found.append(name)
    return found


_SELLER_ROW = re.compile(
    r"(?:(Promoter Group|Promoter|Investor|Individual|Other)\s+)?"
    r"Selling Shareholders?\s+"
    r"(?:Up to\s+)?(\[●\]|[\d,]+)\s+Equity Shares"
    r"(?:\s+(?:of|bearing)\s+face\s+value\s+of\s+₹\s*[\d,.]+\s+each)?"
    r"(?:.{0,80}?aggregating(?:\s+up)?\s+to\s+₹\s*(\[●\]|[\d,]+(?:\.\d+)?)\s*(?:[\d.]+\s+)?(lakhs?|crores?|millions?))?"
    r"(?:\s+(?:Negligible#?|Nil|\d+\.\d+#?))?",
)
_NAME_CUT = re.compile(
    r"Negligible#?\s+|\bNil\s+|\d+\.\d+#?\s+|\(IN ₹\)\s*\*?\s*\^?\s*|#\s+|\*\s*(?=[A-Z])",
    re.I,
)


def _seller_name(name: str) -> str:
    """The person or fund, without the column heading or the previous row's amount."""
    name = _SPACE.sub(" ", name).strip(" ,;^#*")
    if re.search(r"equity share|face value|weighted average|cost of acquisition|\bwaca\b", name, re.I):
        name = re.sub(r"^.*\)\s*", "", name)
        name = re.sub(
            r"^.*\b(?:equity shares?|face value|weighted average|cost of acquisition|waca)\b\s*",
            "",
            name,
            flags=re.I,
        )
    name = re.sub(
        r"^.*aggregating(?:\s+up)?\s+to\s+₹\s*(?:\[●\]|[\d,.]+)\s*(?:lakhs?|crores?|millions?)?\s*(?:Negligible|Nil)?\^?\s*",
        "",
        name,
        flags=re.I,
    )
    name = re.sub(r"^(?:Negligible|Nil)\s+", "", name, flags=re.I)
    name = re.sub(r"^\d{1,3}\s+(?=[A-Z])", "", name)
    return name.strip(" ,;^#*")


def _sellers(text: str) -> list[str]:
    found = []
    seen = set()

    def add(name: str) -> None:
        name = _SPACE.sub(" ", name).strip(" ,;^#*")
        name = re.sub(r"^(?:Negligible|Nil)\s+", "", name)
        name = re.sub(r"^.*\bSELLING SHAREHOLDERS?\s+", "", name, flags=re.I).strip(" ,;^#*")
        key = name.lower().rstrip(".")
        if (
            not name
            or "equity shares" in key
            or key in {"ltd", "limited", "llp", "llc", "lp", "investor", "promoter", "other", "promoter group", "individual", "dr"}
            or key in seen
        ):
            return
        seen.add(key)
        found.append(name)

    for name in re.findall(
        r"([A-Z][A-Za-z0-9&.,'’\- ]{2,70}?)\s+\((?:the\s+)?[\"“]?Selling Shareholder",
        text,
    ):
        add(name)
    # The name sits immediately before the type, and may contain brackets and lowercase words.
    previous = 0
    for match in _SELLER_ROW.finditer(text):
        shares, amount, unit = match.group(2), match.group(3), match.group(4)
        window = text[previous:match.start()][-500:]
        cuts = list(_NAME_CUT.finditer(window))
        if cuts:
            window = window[cuts[-1].end():]
        earlier = list(
            re.finditer(
                r"Equity Shares\b(?:\s+(?:of|bearing)\s+face\s+value\s+of\s+₹\s*[\d,.]+\s+each)?"
                r"(?:.{0,50}?aggregating(?:\s+up)?\s+to\s+₹\s*(?:\[●\]|[\d,.]+)\s*(?:lakhs?|crores?|millions?)?)?",
                window,
                re.I,
            )
        )
        if earlier:
            window = window[earlier[-1].end():]
        window = re.sub(r"^.*\bOFFER FOR SALE\b\s*", "", window, flags=re.I)
        window = re.sub(
            r"^(?:(?:of|bearing)\s+face\s+value\s+of\s+₹\s*[\d,.]+\s+each\s*)",
            "",
            window,
            flags=re.I,
        )
        name = _seller_name(window)
        if (match.group(1) or "").lower() == "other" and (not name or "annexure" in name.lower()):
            name = "Other shareholders"
        if amount and unit and not amount.startswith("["):
            detail = _crore(amount, unit)
        elif shares.startswith("["):
            detail = "share count not stated"
        else:
            detail = f"up to {shares} shares"
        add(f"{name} ({detail})")
        previous = match.end()
    return found[:12]

