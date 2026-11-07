"""Immutable local drafts, explicit review, atomic single-attempt sending."""
import base64
import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from .config import private_dir, get_box

MAX_BYTES = 20 * 1024 * 1024  # Conservative local limit, not an ISDS limit.


@contextmanager
def database():
    root = private_dir()
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / "drafts.sqlite3", timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL, expires REAL NOT NULL, result TEXT)")
        db.commit()
        yield db
    finally:
        db.close()


def digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prepare(alias: str, recipient: str, subject: str, body: str = "", files: list | None = None) -> dict:
    box = get_box(alias)
    if not re.fullmatch(r"[a-z0-9]{7}", recipient):
        raise ValueError("Neplatne ID prijemce.")
    if not subject.strip() or len(subject) > 255:
        raise ValueError("Predmet musi mit 1 az 255 znaku.")
    if not body.strip() and not files:
        raise ValueError("Zprava musi obsahovat text nebo prilohu.")
    if files is not None and not isinstance(files, list):
        raise ValueError("Prilohy musi byt seznam.")
    checked, size = [], len(body.encode("utf-8"))
    for f in files or []:
        if not isinstance(f, dict) or set(f) != {"filename", "mime_type", "content_base64"}:
            raise ValueError("Priloha vyzaduje filename, mime_type a content_base64.")
        name = f["filename"]
        if not name or len(name) > 200 or any(c in name for c in '/\\:\x00') or name in {".", ".."}:
            raise ValueError("Neplatny nazev prilohy.")
        if len(f["content_base64"]) > MAX_BYTES * 4 // 3 + 4:
            raise ValueError("Priloha presahuje mistni limit.")
        raw = base64.b64decode(f["content_base64"], validate=True)
        size += len(raw)
        checked.append(dict(f))
    if size > MAX_BYTES or len(checked) > 50:
        raise ValueError("Mistni limit je 20 MiB a 50 priloh.")
    data = {"alias": box.alias, "box_id": box.box_id, "username": box.username,
            "environment": box.environment, "recipient": recipient,
            "subject": subject, "body": body, "files": checked}
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    draft_id = secrets.token_hex(16)
    with database() as db:
        db.execute("INSERT INTO drafts VALUES (?, ?, ?, 'prepared', ?, NULL)",
                   (draft_id, payload, digest(payload), time.time() + 86400))
        db.commit()
    return preview(draft_id)


def _row(db, draft_id):
    row = db.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if row is None:
        raise ValueError("Navrh neexistuje.")
    if digest(row["payload"]) != row["digest"]:
        raise ValueError("Obsah navrhu byl zmenen.")
    return row


def preview(draft_id: str) -> dict:
    with database() as db:
        row = _row(db, draft_id)
    data = json.loads(row["payload"])
    data.pop("username")
    data["files"] = [{"filename": f["filename"], "mime_type": f["mime_type"],
                      "size_bytes": len(base64.b64decode(f["content_base64"])),
                      "sha256": hashlib.sha256(base64.b64decode(f["content_base64"])).hexdigest()}
                     for f in data["files"]]
    return {"draft_id": draft_id, "digest": row["digest"], "state": row["state"],
            "expires": row["expires"], "message": data,
            "result": json.loads(row["result"]) if row["result"] else None}


def approve(draft_id: str, expected_digest: str) -> None:
    """Local review UI only; never exposed as an MCP tool."""
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        row = _row(db, draft_id)
        if row["state"] != "prepared" or row["expires"] < time.time() or row["digest"] != expected_digest:
            raise ValueError("Navrh nelze schvalit; stav, platnost nebo obsah se zmenil.")
        db.execute("UPDATE drafts SET state='approved', expires=? WHERE id=?", (time.time() + 900, draft_id))
        db.commit()


def send(draft_id: str) -> dict:
    from .services import isds
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        row = _row(db, draft_id)
        if row["state"] != "approved" or row["expires"] < time.time():
            raise PermissionError("Navrh neni schvaleny, vyprsel nebo uz byl pouzit.")
        data = json.loads(row["payload"])
        box = get_box(data["alias"])
        if not box.allow_send:
            raise PermissionError("Odesilani neni pro tento ucet povolene.")
        if (box.box_id, box.username, box.environment) != (data["box_id"], data["username"], data["environment"]):
            raise PermissionError("Konfigurace odesilatele se zmenila. Vytvorte novy navrh.")
        db.execute("UPDATE drafts SET state='sending' WHERE id=?", (draft_id,))
        db.commit()
    try:
        result = isds.send_message(box, data["recipient"], data["subject"], data["body"], data["files"])
        if not result.get("message_id"):
            raise RuntimeError("ISDS nevratilo ID zpravy.")
    except Exception:
        with database() as db:
            db.execute("UPDATE drafts SET state='uncertain' WHERE id=?", (draft_id,))
            db.commit()
        raise RuntimeError("Vysledek odeslani je nejisty. Overte odeslane zpravy; neopakujte automaticky.") from None
    with database() as db:
        db.execute("UPDATE drafts SET state='sent', result=? WHERE id=?", (json.dumps(result), draft_id))
        db.commit()
    return result
