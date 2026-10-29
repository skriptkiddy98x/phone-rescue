"""Turn a finished mobilebackup2 backup into readable exports:
messages (+ attachments), contacts, call history and best-effort location history.

Everything is parsed from the backup's own SQLite databases; we never modify the
backup. Each parser is isolated so one failure does not stop the others.
"""
from __future__ import annotations

import csv
import shutil
import sqlite3
from pathlib import Path

from phonerescue.common.util import cocoa_to_dt, fmt, safe_name


def _manifest(backup_dir: Path):
    """Return (device_dir, {relativePath.lower(): content_path})."""
    device_dir = next((p for p in backup_dir.iterdir()
                       if p.is_dir() and (p / "Manifest.db").exists()), None)
    if device_dir is None:
        return None, {}
    con = sqlite3.connect(f"file:{(device_dir / 'Manifest.db').as_posix()}?immutable=1", uri=True)
    index = {}
    for file_id, domain, rel in con.execute(
            "select fileID, domain, relativePath from Files where flags = 1"):
        if rel:
            index[(domain or "", rel)] = device_dir / file_id[:2] / file_id
    con.close()
    return device_dir, index


def _find(index: dict, suffix: str):
    suffix = suffix.lower()
    for (domain, rel), path in index.items():
        if rel.lower().endswith(suffix) and path.exists():
            return path
    return None


def _ro(path: Path):
    return sqlite3.connect(f"file:{path.as_posix()}?immutable=1", uri=True)


def _messages(index, out: Path, backup_dir, device_dir) -> str:
    db = _find(index, "Library/SMS/sms.db")
    if not db:
        return "Messages: sms.db not in backup"
    con = _ro(db)
    rows = []
    try:
        q = """
            select m.ROWID, m.date, m.is_from_me, m.text, h.id, m.cache_has_attachments
            from message m left join handle h on h.ROWID = m.handle_id
            order by m.date
        """
        for rid, date, mine, text, handle, has_att in con.execute(q):
            rows.append({
                "date": fmt(cocoa_to_dt(date)),
                "direction": "sent" if mine else "received",
                "contact": handle or "",
                "text": (text or "").replace("\r", " ").replace("\n", " "),
                "has_attachment": bool(has_att),
                "rowid": rid,
            })
    except sqlite3.Error as e:
        con.close()
        return f"Messages: could not parse sms.db ({e})"

    msg_dir = out / "messages"
    msg_dir.mkdir(parents=True, exist_ok=True)
    with open(msg_dir / "messages.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "direction", "contact", "text",
                                          "has_attachment", "rowid"])
        w.writeheader()
        w.writerows(rows)

    # attachments
    att_rows = []
    copied = 0
    try:
        q = """
            select a.filename, a.transfer_name, a.mime_type, a.total_bytes, a.created_date
            from attachment a
        """
        att_dir = msg_dir / "attachments"
        for filename, tname, mime, size, created in con.execute(q):
            name = tname or (filename or "").split("/")[-1]
            # attachments live under MediaDomain Library/SMS/Attachments/...
            src = None
            if filename:
                rel = filename.replace("~/", "").lstrip("/")
                src = _find(index, rel.split("Library/SMS/")[-1]) if "Library/SMS/" in rel else None
            status = "listed"
            if src and src.exists():
                dst = att_dir / safe_name(name)
                dst.parent.mkdir(parents=True, exist_ok=True)
                i = 1
                while dst.exists():
                    dst = dst.with_name(f"{dst.stem}_{i}{dst.suffix}")
                    i += 1
                shutil.copy2(src, dst)
                copied += 1
                status = "saved"
            att_rows.append({"date": fmt(cocoa_to_dt(created)), "name": name,
                             "mime": mime or "", "size": size or 0, "status": status})
    except sqlite3.Error:
        pass
    con.close()
    if att_rows:
        with open(msg_dir / "attachments.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["date", "name", "mime", "size", "status"])
            w.writeheader()
            w.writerows(att_rows)
    return f"Messages: {len(rows)} messages, {len(att_rows)} attachments ({copied} files saved)"


def _contacts(index, out: Path) -> str:
    db = _find(index, "Library/AddressBook/AddressBook.sqlitedb")
    if not db:
        return "Contacts: AddressBook not in backup"
    con = _ro(db)
    try:
        people = {}
        for rid, first, last, org in con.execute(
                "select ROWID, First, Last, Organization from ABPerson"):
            name = " ".join(x for x in (first, last) if x) or (org or "")
            people[rid] = {"name": name, "org": org or "", "phones": [], "emails": []}
        for rec, prop, value in con.execute(
                "select record_id, property, value from ABMultiValue"):
            person = people.get(rec)
            if not person or value is None:
                continue
            if prop == 3:
                person["phones"].append(str(value))
            elif prop == 4:
                person["emails"].append(str(value))
    except sqlite3.Error as e:
        con.close()
        return f"Contacts: could not parse AddressBook ({e})"
    con.close()
    rows = [{"name": p["name"], "org": p["org"],
             "phones": "; ".join(p["phones"]), "emails": "; ".join(p["emails"])}
            for p in people.values()]
    with open(out / "contacts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "org", "phones", "emails"])
        w.writeheader()
        w.writerows(rows)
    return f"Contacts: {len(rows)}"


def _calls(index, out: Path) -> str:
    db = _find(index, "Library/CallHistoryDB/CallHistory.storedata") or _find(index, "call_history.db")
    if not db:
        return "Calls: call history not in backup"
    con = _ro(db)
    rows = []
    try:
        for date, dur, addr, originated, answered in con.execute(
                "select ZDATE, ZDURATION, ZADDRESS, ZORIGINATED, ZANSWERED from ZCALLRECORD"):
            if isinstance(addr, (bytes, bytearray)):
                addr = addr.decode("utf-8", "replace")
            rows.append({
                "date": fmt(cocoa_to_dt(date)),
                "number": addr or "",
                "direction": "outgoing" if originated else "incoming",
                "answered": bool(answered),
                "duration_s": int(dur or 0),
            })
    except sqlite3.Error as e:
        con.close()
        return f"Calls: could not parse ({e})"
    con.close()
    rows.sort(key=lambda r: r["date"])
    with open(out / "calls.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "number", "direction", "answered", "duration_s"])
        w.writeheader()
        w.writerows(rows)
    return f"Calls: {len(rows)}"


def _locations(index, out: Path) -> str:
    """Best-effort: any table carrying latitude/longitude columns (routined/knowledgeC)."""
    candidates = [_find(index, "com.apple.routined/Cache.sqlite"),
                  _find(index, "com.apple.routined/Local.sqlite"),
                  _find(index, "Knowledge/knowledgeC.db")]
    rows = []
    for db in filter(None, candidates):
        try:
            con = _ro(db)
            tables = [r[0] for r in con.execute(
                "select name from sqlite_master where type='table'")]
            for t in tables:
                cols = [c[1] for c in con.execute(f'pragma table_info("{t}")')]
                lat = next((c for c in cols if c.upper().endswith("LATITUDE")), None)
                lon = next((c for c in cols if c.upper().endswith("LONGITUDE")), None)
                if not (lat and lon):
                    continue
                tcol = next((c for c in cols if "TIMESTAMP" in c.upper()
                             or c.upper().endswith("DATE") or c.upper().endswith("TIME")), None)
                sel = f'select "{lat}","{lon}"' + (f',"{tcol}"' if tcol else "") + f' from "{t}"'
                for row in con.execute(sel):
                    la, lo = row[0], row[1]
                    if la in (None, 0) and lo in (None, 0):
                        continue
                    when = cocoa_to_dt(row[2]) if tcol and len(row) > 2 else None
                    rows.append({"date": fmt(when), "latitude": la, "longitude": lo,
                                 "source": f"{db.name}:{t}"})
            con.close()
        except sqlite3.Error:
            continue
    if not rows:
        return "Locations: no location database present in this backup"
    rows.sort(key=lambda r: r["date"])
    with open(out / "locations.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "latitude", "longitude", "source"])
        w.writeheader()
        w.writerows(rows)
    return f"Locations: {len(rows)} points"


def extract_all(backup_dir: Path, out: Path, progress=print) -> list[str]:
    device_dir, index = _manifest(backup_dir)
    if not index:
        return ["Backup: Manifest.db not found; nothing to extract"]
    tasks = [
        ("messages", lambda: _messages(index, out, backup_dir, device_dir)),
        ("contacts", lambda: _contacts(index, out)),
        ("calls", lambda: _calls(index, out)),
        ("locations", lambda: _locations(index, out)),
    ]
    results = []
    for label, fn in tasks:
        try:
            line = fn()
        except Exception as e:  # noqa: BLE001
            line = f"{label}: error ({e})"
        progress("  " + line)
        results.append(line)
    return results
