"""Telegram bot for new SEBI DRHP, UDRHP, and RHP filings.

Run:  python -m rhpbot.bot --once
      python -m rhpbot.bot --samples
The token is read from RHP_BOT_TOKEN. --samples resends one DRHP, one RHP,
and one UDRHP already on SEBI's first page, without treating them as new.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from rhpbot.sebi import Filing, _get, attach, filings
from rhpbot.summary import has_business_section, render, summarize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "rhpbot", "state", "filings.json")
MAX_BYTES = 48 * 1024 * 1024

WELCOME = (
    "RHP bot is on.\n"
    "I post a new DRHP, UDRHP, or RHP when it is filed with SEBI, with the "
    "issue size, fresh issue, offer for sale, bankers, and selling shareholders "
    "when the document states them."
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--samples", action="store_true")
    parser.add_argument("--kind", choices=("DRHP", "UDRHP", "RHP"))
    parser.add_argument("--company", action="append", default=[])
    args = parser.parse_args()
    if args.dry_run:
        for filing in filings():
            print(f"{filing.filed}  {filing.kind}  {filing.company}")
        return
    token = _load_token()
    state = _load_state()
    _ensure_chat(state)
    if args.samples:
        _send_samples(token, state, args.kind, args.company)
        return
    try:
        _learn_groups(
            token,
            state,
            "This group is connected. New DRHP, UDRHP, and RHP filings will be posted here.",
        )
    except Exception as exc:
        print("groups skipped: " + _redact(exc, token), flush=True)
    _poll(token, state)
    _save_state(state)


def _send_samples(token: str, state: dict, kind: str | None = None, companies: list[str] | None = None) -> None:
    """One already-filed example of each document, so the chat can be reviewed."""
    try:
        found = filings()
    except Exception as exc:
        print("feed error: " + _redact(exc, token), flush=True)
        return
    chosen = _pick_named(found, companies or []) or _pick_samples(found)
    if kind:
        chosen = [item for item in chosen if item.kind == kind]
    if not state["chats"]:
        print("RHP_CHAT_ID is missing", flush=True)
        return
    for filing in chosen:
        text, files = _prepare(filing)
        text = "Sample of a filing already on SEBI\n\n" + text
        _broadcast(token, state, text, files)
        print(f"sent {filing.kind} {filing.company} ({len(files)} files)", flush=True)
    print(f"{len(chosen)} samples, {len(state['chats'])} chats", flush=True)


def _pick_named(found: list[Filing], companies: list[str]) -> list[Filing]:
    chosen = []
    for hint in companies:
        key = hint.strip().lower()
        if not key:
            continue
        match = next((item for item in found if key in item.company.lower()), None)
        if match is None:
            print(f"not on the current page: {hint}", flush=True)
            continue
        if match not in chosen:
            chosen.append(match)
    return chosen


def _pick_samples(found: list[Filing]) -> list[Filing]:
    preferred = (("DRHP", "il jin"), ("RHP", "mahanadi"), ("UDRHP", "carlsberg"))
    chosen = []
    for kind, hint in preferred:
        match = next((item for item in found if item.kind == kind and hint in item.company.lower()), None)
        if match is None:
            match = next((item for item in found if item.kind == kind), None)
        if match is not None:
            chosen.append(match)
    return chosen


def _poll(token: str, state: dict) -> None:
    try:
        found = filings()
    except Exception as exc:
        print("feed error: " + _redact(exc, token), flush=True)
        return
    seen = set(state["seen"])
    fresh = [item for item in found if item.id not in seen]
    if not state["primed"]:
        state["primed"] = True
        state["seen"] = _trim([item.id for item in found])
        print(f"primed {len(found)} filings, 0 sent", flush=True)
        return
    state["seen"] = _trim(state["seen"] + [item.id for item in fresh])
    for filing in fresh:
        text, files = _prepare(filing)
        _broadcast(token, state, text, files)
        state["recent"].append({"text": text, "id": filing.id})
    state["recent"] = state["recent"][-30:]
    print(f"{len(fresh)} new filings, {len(state['chats'])} chats", flush=True)


def _prepare(filing: Filing) -> tuple[str, list[tuple[str, bytes]]]:
    current = filing
    try:
        current = attach(filing, _get(filing.page))
    except Exception as exc:
        print(f"page skipped: {exc}", flush=True)
    fields: dict[str, str] = {}
    files: list[tuple[str, bytes]] = []
    if current.abridged:
        try:
            data = _download(current.abridged)
            fields = summarize(_pdf_text(data, full=False))
            files.append((_filename(current, "abridged"), data))
        except Exception as exc:
            print(f"abridged skipped: {exc}", flush=True)
    if not fields and current.full:
        try:
            fields = summarize(_pdf_text(_download(current.full), full=True))
        except Exception as exc:
            print(f"summary skipped: {exc}", flush=True)
    text = render(current.kind, current.company, current.filed, fields, current.page, current.full)
    return text, files


def _pdf_text(data: bytes, full: bool) -> str:
    """Cover, plus the primary-business section when the prospectus is the full document.

    An abridged prospectus is that summary. A full prospectus prints the same
    section after the definitions and the risk factors, so those pages are not
    part of the summary.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = reader.pages
    if not full:
        return "\n".join((page.extract_text() or "") for page in pages[:30])
    cover = [(page.extract_text() or "") for page in pages[:12]]
    if has_business_section("\n".join(cover)):
        return "\n".join(cover)
    previous = cover[-1] if cover else ""
    for index in range(12, min(len(pages), 140)):
        text = pages[index].extract_text() or ""
        if has_business_section(previous[-500:] + "\n" + text):
            following = pages[index + 1].extract_text() or "" if index + 1 < len(pages) else ""
            return "\n".join(cover + [text, following])
        previous = text
    return "\n".join(cover)


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        length = response.headers.get("Content-Length")
        if length and length.isdigit() and int(length) > MAX_BYTES:
            raise ValueError("file is too large to attach")
        chunks = []
        total = 0
        while True:
            block = response.read(65536)
            if not block:
                break
            total += len(block)
            if total > MAX_BYTES:
                raise ValueError("file is too large to attach")
            chunks.append(block)
    return b"".join(chunks)


def _filename(filing: Filing, label: str) -> str:
    raw = f"{filing.company} {filing.kind} {label}.pdf"
    cleaned = re.sub(r'[<>:"/\\|?*\n\r]+', " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:100]


def _broadcast(token: str, state: dict, text: str, files: list[tuple[str, bytes]]) -> None:
    for chat_id in list(state["chats"]):
        if chat_id not in state["chats"]:
            continue
        target = chat_id
        try:
            _send(token, target, text)
        except RuntimeError as exc:
            moved = _migrated_chat_id(exc)
            if moved is None:
                print(f"send to {chat_id} failed: {_redact(exc, token)}", flush=True)
                continue
            already = moved in state["chats"]
            _replace_chat(state, chat_id, moved)
            print(f"group {chat_id} moved to {moved}", flush=True)
            if already:
                continue
            target = moved
            try:
                _send(token, target, text)
            except RuntimeError as exc2:
                print(f"send to {moved} failed: {_redact(exc2, token)}", flush=True)
                continue
        for name, data in files:
            try:
                _send_file(token, target, name, data)
            except RuntimeError as exc:
                print(f"send to {target} failed: {_redact(exc, token)}", flush=True)


def _send(token: str, chat_id: int, text: str) -> None:
    _api(token, "sendMessage", {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True})
    time.sleep(0.4)


def _send_file(token: str, chat_id: int, filename: str, data: bytes) -> None:
    boundary = "----RhpBotBoundary7f3a9c"
    kind = "application/pdf" if filename.lower().endswith(".pdf") else "application/octet-stream"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        f"{chat_id}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
        f"Content-Type: {kind}\r\n\r\n"
    ).encode()
    body = head + data + f"\r\n--{boundary}--\r\n".encode()
    _api(
        token,
        "sendDocument",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        timeout=90,
    )
    time.sleep(0.4)


def _api(token: str, method: str, payload: dict | None = None, timeout: int = 30, data: bytes | None = None, headers: dict | None = None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    if data is None:
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"} if data else {}
    last = "no response"
    for attempt in range(5):
        request = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode())
            if not body.get("ok"):
                raise RuntimeError(f"{method} refused")
            return body.get("result")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            last = f"{method} {exc.code} {_redact(detail, token)}"
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                break
        except Exception as exc:
            last = f"{method} {_redact(exc, token)}"
            if attempt == 4:
                break
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(last)


def _load_token() -> str:
    path = os.path.join(ROOT, ".env")
    token = os.environ.get("RHP_BOT_TOKEN", "")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.startswith("RHP_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"')
    if not token:
        sys.exit("RHP_BOT_TOKEN is missing")
    return token


def _group_event(update: dict) -> tuple[str, int] | None:
    """A group join or leave. Private chats are left to the saved chat id."""
    member = update.get("my_chat_member")
    if member:
        chat = member.get("chat") or {}
        if chat.get("type") not in ("group", "supergroup"):
            return None
        chat_id = chat.get("id")
        status = (member.get("new_chat_member") or {}).get("status")
        if not isinstance(chat_id, int):
            return None
        if status in ("member", "administrator", "creator"):
            return ("join", chat_id)
        if status in ("left", "kicked"):
            return ("leave", chat_id)
        return None
    chat = (update.get("message") or {}).get("chat") or {}
    chat_id = chat.get("id")
    if chat.get("type") in ("group", "supergroup") and isinstance(chat_id, int):
        return ("join", chat_id)
    return None


def _apply_group_event(state: dict, event: tuple[str, int]) -> str:
    kind, chat_id = event
    welcomed = state.setdefault("welcomed", [])
    if kind == "join":
        added = chat_id not in state["chats"]
        if added:
            state["chats"].append(chat_id)
        if chat_id not in welcomed:
            welcomed.append(chat_id)
        return "added" if added else "kept"
    removed = chat_id in state["chats"]
    state["chats"] = [item for item in state["chats"] if item != chat_id]
    state["welcomed"] = [item for item in welcomed if item != chat_id]
    return "removed" if removed else "kept"


def _migrated_chat_id(exc: BaseException) -> int | None:
    text = str(exc)
    key = '"migrate_to_chat_id":'
    start = text.find(key)
    if start < 0:
        return None
    raw = []
    for char in text[start + len(key):].lstrip():
        if char == "-" or char.isdigit():
            raw.append(char)
        else:
            break
    if not raw or raw == ["-"]:
        return None
    return int("".join(raw))


def _replace_chat(state: dict, old_id: int, new_id: int) -> None:
    def swap(items: list) -> list:
        result = []
        for item in items:
            item = new_id if item == old_id else item
            if item not in result:
                result.append(item)
        return result

    state["chats"] = swap(state.get("chats", []))
    state["welcomed"] = swap(state.get("welcomed", []))


def _note_group(token: str, state: dict, chat_id: int, note: str) -> None:
    print(f"group {chat_id}", flush=True)
    try:
        _send(token, chat_id, note)
    except RuntimeError as exc:
        moved = _migrated_chat_id(exc)
        if moved is None:
            print(f"send to {chat_id} failed: {_redact(exc, token)}", flush=True)
            return
        already = moved in state["chats"]
        _replace_chat(state, chat_id, moved)
        print(f"group {chat_id} moved to {moved}", flush=True)
        if already:
            return
        try:
            _send(token, moved, note)
        except RuntimeError as exc2:
            print(f"send to {moved} failed: {_redact(exc2, token)}", flush=True)


def _settle_groups(token: str, state: dict) -> None:
    """Drop a basic group id after Telegram upgrades that group to a supergroup."""
    for chat_id in list(state["chats"]):
        if chat_id >= 0 or str(chat_id).startswith("-100"):
            continue
        try:
            _api(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"})
        except RuntimeError as exc:
            moved = _migrated_chat_id(exc)
            if moved is None:
                print(f"group {chat_id} skipped: {_redact(exc, token)}", flush=True)
                continue
            _replace_chat(state, chat_id, moved)
            print(f"group {chat_id} moved to {moved}", flush=True)


def _learn_groups(token: str, state: dict, note: str) -> None:
    """Remember a group the bot was added to, without resending filings already seen."""
    _settle_groups(token, state)
    for _ in range(10):
        updates = _api(
            token,
            "getUpdates",
            {
                "timeout": 0,
                "offset": state.get("offset", 0),
                "allowed_updates": ["message", "my_chat_member"],
            },
            timeout=20,
        )
        if not updates:
            return
        for update in updates:
            state["offset"] = int(update["update_id"]) + 1
            event = _group_event(update)
            if event is None:
                continue
            result = _apply_group_event(state, event)
            if result == "added":
                _note_group(token, state, event[1], note)
            elif result == "removed":
                print(f"left {event[1]}", flush=True)


def _ensure_chat(state: dict) -> None:
    raw = os.environ.get("RHP_CHAT_ID", "").strip()
    if not raw:
        return
    chat_id = int(raw)
    if chat_id not in state["chats"]:
        state["chats"].append(chat_id)
    if chat_id not in state["welcomed"]:
        state["welcomed"].append(chat_id)


def _load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {"seen": [], "chats": [], "welcomed": [], "recent": [], "primed": False, "offset": 0}
    with open(STATE_PATH, encoding="utf-8") as handle:
        state = json.load(handle)
    for key, value in (("seen", []), ("chats", []), ("welcomed", []), ("recent", []), ("primed", False), ("offset", 0)):
        state.setdefault(key, value)
    return state


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, sort_keys=True, separators=(",", ":"))
    os.replace(tmp, STATE_PATH)


def _trim(ids: list[str]) -> list[str]:
    kept = []
    seen = set()
    for item_id in ids:
        if item_id not in seen:
            seen.add(item_id)
            kept.append(item_id)
    return kept[-5000:]


def _redact(value, token: str) -> str:
    return str(value).replace(token, "<token>")


if __name__ == "__main__":
    main()
