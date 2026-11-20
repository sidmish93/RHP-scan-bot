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
from rhpbot.summary import render, summarize

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
    args = parser.parse_args()
    if args.dry_run:
        for filing in filings():
            print(f"{filing.filed}  {filing.kind}  {filing.company}")
        return
    token = _load_token()
    state = _load_state()
    _ensure_chat(state)
    if args.samples:
        _send_samples(token, state)
        return
    _poll(token, state)
    _save_state(state)


def _send_samples(token: str, state: dict) -> None:
    """One already-filed example of each document, so the chat can be reviewed."""
    try:
        found = filings()
    except Exception as exc:
        print("feed error: " + _redact(exc, token), flush=True)
        return
    chosen = _pick_samples(found)
    if not state["chats"]:
        print("RHP_CHAT_ID is missing", flush=True)
        return
    for filing in chosen:
        text, files = _prepare(filing)
        text = "Sample of a filing already on SEBI\n\n" + text
        _broadcast(token, state, text, files)
        print(f"sent {filing.kind} {filing.company} ({len(files)} files)", flush=True)
    print(f"{len(chosen)} samples, {len(state['chats'])} chats", flush=True)


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
    source = current.abridged or current.full
    if source:
        try:
            data = _download(source)
            pages = 20 if current.abridged else 8
            fields = summarize(_pdf_text(data, pages))
            if current.abridged:
                files.append((_filename(current, "abridged"), data))
        except Exception as exc:
            print(f"summary skipped: {exc}", flush=True)
    if current.full and current.full != current.abridged:
        try:
            files.append((_filename(current, "prospectus"), _download(current.full)))
        except Exception as exc:
            print(f"prospectus skipped: {exc}", flush=True)
    text = render(current.kind, current.company, current.filed, fields, current.page, current.full)
    return text, files


def _pdf_text(data: bytes, pages: int) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:pages])


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
        try:
            _send(token, chat_id, text)
            for name, data in files:
                _send_file(token, chat_id, name, data)
        except RuntimeError as exc:
            print(f"send to {chat_id} failed: {_redact(exc, token)}", flush=True)


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
