"""Export media and personal data from an authorised Android phone via adb.

Uses only documented adb features: `adb pull` for shared storage and
`adb shell content query` for the system content providers (contacts, SMS, call log).
App-private storage is only reachable on a rooted device, which is detected and used
only if present.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from phonerescue.android.connect import is_rooted, run

MEDIA_DIRS = [
    "/sdcard/DCIM",
    "/sdcard/Pictures",
    "/sdcard/Movies",
    "/sdcard/Download",
    "/sdcard/WhatsApp/Media",
    "/sdcard/Android/media/com.whatsapp/WhatsApp/Media",
]

PROVIDERS = {
    "contacts": "content://com.android.contacts/data/phones",
    "sms": "content://sms",
    "call_log": "content://call_log/calls",
}


def pull_media(adb: str, out: Path, progress=print) -> int:
    dest = out / "media"
    dest.mkdir(parents=True, exist_ok=True)
    pulled = 0
    for remote in MEDIA_DIRS:
        exists = run(adb, "shell", f'[ -d "{remote}" ] && echo yes || echo no').strip()
        if "yes" not in exists:
            continue
        target = dest / remote.strip("/").replace("/", "_")
        target.mkdir(parents=True, exist_ok=True)
        progress(f"  pulling {remote} ...")
        run(adb, "pull", "-a", remote, str(target), timeout=1800)
        pulled += sum(1 for _ in target.rglob("*") if _.is_file())
    progress(f"media files pulled: {pulled}")
    return pulled


def _parse_content_rows(text: str) -> list[dict]:
    """Parse `adb shell content query` output lines into dicts."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("Row:"):
            continue
        body = line.split(" ", 1)[1] if " " in line else ""
        fields = {}
        for pair in re.split(r", (?=[A-Za-z0-9_]+=)", body):
            if "=" in pair:
                k, v = pair.split("=", 1)
                fields[k.strip()] = v
        rows.append(fields)
    return rows


def dump_provider(adb: str, name: str, uri: str, out: Path, progress=print) -> str:
    try:
        text = run(adb, "shell", "content", "query", "--uri", uri, timeout=300)
    except Exception as e:  # noqa: BLE001
        return f"{name}: query failed ({e})"
    if "Error" in text and "Row:" not in text:
        return f"{name}: not accessible ({text.strip().splitlines()[0] if text.strip() else 'permission denied'})"
    rows = _parse_content_rows(text)
    if not rows:
        return f"{name}: 0 rows (provider may be restricted on this Android version)"
    fields = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return f"{name}: {len(rows)} rows"


def export_all(adb: str, out: Path, progress=print) -> list[str]:
    results = []
    pulled = pull_media(adb, out, progress)
    results.append(f"Media: {pulled} files")
    for name, uri in PROVIDERS.items():
        line = dump_provider(adb, name, uri, out, progress)
        progress("  " + line)
        results.append(line)
    if is_rooted(adb):
        results.append("Root detected: app-private storage is reachable "
                       "(rerun with care; not pulled automatically).")
    else:
        results.append("No root: app-private storage (e.g. in-app caches) was not accessible.")
    return results
