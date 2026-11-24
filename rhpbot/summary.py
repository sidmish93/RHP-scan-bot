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
    r"(?:\s+(?:of|bearing)\s+face\s+value\s+of\s+₹\s*(?P<face>[\d,.]+)(?:\s*/-)?\s+each)?"
    r".{0,180}?"
    r"aggregating(?:\s+up)?\s+to\s+₹?\s*(?P<amount>\[(?:●|•)\]|[\d,]+(?:\.\d+)?)\s*"
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

    banks = _bankers(collapsed)
    if banks:
        fields["bankers"] = ", ".join(banks)

    sellers = _sellers(collapsed)
    if fields.get("ofs") == "none":
        fields["sellers"] = "none"
    elif sellers:
        fields["sellers"] = "; ".join(sellers)

    business = _business(text or "")
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
    if full:
        lines.append(full)
    elif page:
        lines.append(page)
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
    matches = list(_SIZE.finditer(data))
    # "NIL" between two size cells is an empty offer for sale. The second cell is the total.
    if len(matches) >= 2 and re.search(r"\bnil\b", data[matches[0].end():matches[1].start()], re.I):
        fields = {
            "fresh": _size_text(matches[0]),
            "ofs": "none",
            "total": _size_text(matches[1]),
        }
        return fields
    labels = ("fresh", "ofs", "total")
    fields: dict[str, str] = {}
    for label, match in zip(labels, matches):
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
    r"summary of (?:the )?primary business(?:\s+of\s+(?:our|the)\s+company)?"
    r"|(?<![A-Za-z])primary business(?=\s+[a-h][.)])",
    re.I,
)
# The next outline item. The period that closes the previous sentence stays in that sentence.
_OUTLINE = re.compile(
    r"\s+\(?[a-h]\)(?=\s+[A-Z])"
    r"|\s+[a-h][.)](?=\s+[A-Z])"
    r"|\s+(?:[1-9]|1[0-2])[.)](?=\s+[A-Z])"
    r"|(?:^|(?<! [a-h]\.\s)(?<=\.\s))business overview\b"
    r"|➢",
    re.I,
)
# A schedule label such as "Manufacturing and Selling:" is the next item.
# Case-sensitive so an ordinary sentence is not cut at a lowercase word.
_COLON_HEADING = re.compile(
    r"(?<=\.)\s+[A-Z][A-Za-z&]+"
    r"(?:\s+(?:and|of|the|for|in|to|by|our|or|&|[A-Z][A-Za-z&]+)){0,6}"
    r":\s+(?=[A-Z])"
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


def needs_full_prospectus(fields: dict[str, str]) -> bool:
    """An abridged file can be a checklist with no offer. The prospectus still has to be read."""
    if not any(fields.get(key) for key in ("fresh", "ofs", "total")):
        return True
    return _poor_business(fields.get("business", ""))


def prefer_fields(primary: dict[str, str], fallback: dict[str, str]) -> dict[str, str]:
    """Keep a real description and fill whatever the first document left out."""
    chosen = dict(primary)
    for key, value in fallback.items():
        if key == "business" and _poor_business(chosen.get("business", "")) and not _poor_business(value):
            chosen["business"] = value
        elif key not in chosen:
            chosen[key] = value
    if chosen.get("ofs") == "none":
        chosen["sellers"] = "none"
    return chosen


def _poor_business(text: str) -> bool:
    """A checklist or a pointer to another chapter, not a description of the company."""
    low = (text or "").lower()
    if len(low) < 25:
        return True
    return "➢" in text or "for further details" in low


def _business(text: str) -> str:
    """The prose under the primary-business heading, through the next heading.

    The paragraph may open with the company's name. When that heading is only a
    label, the description is the first lettered subsection. A later heading,
    including one that sits on its own line, is the next item. A checklist that
    only points at a later chapter is not the description.
    """
    end = _section_end(text)
    if end >= 0:
        region = _cut_at_heading_line(text[end:end + 6000])
        body = _clean_business(_business_body(_SPACE.sub(" ", region)))
        if not _poor_business(body):
            return body
        # The opening sentence is already in this section. A later chapter is not it.
        return _engaged_paragraph(_SPACE.sub(" ", text[end:]), from_start=True)
    return _engaged_paragraph(_SPACE.sub(" ", text))


def _clean_business(body: str) -> str:
    body = re.sub(r"^(?:overview of the business|our business|overview)\s*[:\-–—]?\s*", "", body, flags=re.I)
    body = re.sub(
        r"\s*For (?:further|more) (?:details|information), (?:please\s+)?(?:see|refer to)\b.*$",
        "",
        body,
        flags=re.I,
    )
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


def _chapter_start(text: str) -> int:
    """The business chapter, not the contents line that points at it."""
    for match in re.finditer(r"\bOUR BUSINESS\b", text or "", re.I):
        after = text[match.end():match.end() + 30]
        if re.match(r"\s*\.{3,}", after) or re.match(r"\s+STRATEG", after, re.I):
            continue
        return match.end()
    return -1


def _engaged_paragraph(text: str, from_start: bool = False) -> str:
    """The sentence that says what the company does, after the chapter's disclaimer."""
    if from_start:
        window = text or ""
    else:
        start = _chapter_start(text)
        window = text[start:] if start >= 0 else text or ""
    match = re.search(
        r"([A-Z][^.]{0,160}?\b(?:is|are) engaged in the business of\b[^.]*\.)",
        window,
        re.I,
    )
    if not match:
        return ""
    sentence = re.sub(r"^(?:overview|our business)\s+", "", match.group(1), flags=re.I).strip()
    opened = re.search(r"\b(?:We|Our Company)\b(?= (?:is|are) engaged\b)", sentence)
    if opened:
        sentence = sentence[opened.start():]
    follow = re.match(r"\s+((?:Through|Our|The|These|This)\b[^.]*\.)", window[match.end():])
    if follow:
        sentence = f"{sentence} {follow.group(1).strip()}"
    sentence = _SPACE.sub(" ", sentence).strip()
    return "" if _poor_business(sentence) else sentence


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
    # The business chapter often starts at a bare "Overview", after the disclaimer.
    for match in re.finditer(r"\bOverview\b", text or ""):
        before = text[max(0, match.start() - 24):match.start()]
        if re.search(r"industry\s*$", before, re.I):
            continue
        after = text[match.end():match.end() + 80]
        if re.match(r"\s*(?:We|Our Company|The Company)\b", after):
            return match.end()
    return -1


def _cut_at_heading_line(region: str) -> str:
    """Stop before a heading that the line break still separates from the paragraph."""
    if "\n" not in region:
        return region
    kept: list[str] = []
    seen_sentence = False
    blank = False
    previous_ended = False
    for line in region.split("\n"):
        stripped = re.sub(r"[ \t]+", " ", line).strip()
        words = re.findall(r"[A-Za-z]+", stripped)
        # A short heading can sit on the next line with no blank line between.
        # A wrapped sentence is not a heading, and a long heading still needs a blank line.
        short_heading = _is_heading_line(stripped) and 1 <= len(words) <= 4
        if seen_sentence and _is_heading_line(stripped) and (
            blank or _hard_heading(stripped) or (previous_ended and short_heading)
        ):
            break
        kept.append(line)
        if not stripped:
            blank = True
            continue
        blank = False
        previous_ended = stripped.endswith((".", "!", "?"))
        if "." in stripped:
            seen_sentence = True
    return "\n".join(kept)


def _hard_heading(line: str) -> bool:
    """An outline mark or a short label ending in a colon, not a wrapped sentence."""
    if not line:
        return False
    if line[0] in "➢•":
        return True
    if re.match(r"\(?[a-h][.)]\s+\S", line, re.I):
        return True
    if re.match(r"(?:[1-9]|1[0-2])[.)]\s+\S", line):
        return True
    words = re.findall(r"[A-Za-z]+", line)
    return line.endswith(":") and 1 <= len(words) <= 8 and len(line) <= 80


def _is_heading_line(line: str) -> bool:
    """A schedule heading, not a line of the description that happens to wrap."""
    if not line or len(line) > 160 or line[-1] in ".;,":
        return False
    if re.search(r"\.\s", line) or re.match(r"\(?\s*source\b", line, re.I):
        return False
    if _hard_heading(line):
        return True
    words = re.findall(r"[A-Za-z]+", line)
    if not 2 <= len(words) <= 16 or "," in line:
        return False
    small = {"a", "an", "and", "of", "the", "for", "in", "to", "by", "our", "or", "on", "with"}
    return all(word.lower() in small or word[0].isupper() for word in words)


def _business_body(region: str) -> str:
    marks = sorted(
        [*_OUTLINE.finditer(region), *_COLON_HEADING.finditer(region)],
        key=lambda match: match.start(),
    )
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
    # A cover table can list the name, the type, and the share count, with no rupee cell.
    if not found:
        for match in re.finditer(
            r"([A-Z][A-Za-z0-9&.,'’\- ]{2,80}?)\s+"
            r"(?:Promoter Group|Promoter|Investor|Individual|Other)\s+"
            r"Selling Shareholders?\s+"
            r"([\d,]+)\b",
            text,
        ):
            add(f"{match.group(1).strip(' ,')} ({match.group(2)} shares)")
    return found[:12]

