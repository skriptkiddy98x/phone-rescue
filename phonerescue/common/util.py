"""Small shared helpers."""
from __future__ import annotations

import hashlib
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Apple's two epochs.
COCOA_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)   # CoreData / CFAbsoluteTime, seconds
MAC_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc)     # QuickTime mvhd, seconds


async def aw(value: Any) -> Any:
    """Await `value` if it is awaitable, otherwise return it.

    pymobiledevice3 switched several calls to async; this lets the same code run
    against both old and new releases.
    """
    if inspect.isawaitable(value):
        return await value
    return value


def cocoa_to_dt(seconds: float | int | None):
    if not seconds:
        return None
    # Some tables store nanoseconds.
    if seconds > 1e11:
        seconds = seconds / 1e9
    try:
        return (COCOA_EPOCH + timedelta(seconds=seconds)).astimezone()
    except (OverflowError, OSError):
        return None


def mac_to_dt(seconds: float | int | None):
    if not seconds:
        return None
    try:
        return (MAC_EPOCH + timedelta(seconds=seconds)).astimezone()
    except (OverflowError, OSError):
        return None


def fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def safe_name(text: str, maxlen: int = 100) -> str:
    import re
    cleaned = re.sub(r"[^\w .\-]", "_", text).strip() or "item"
    return cleaned[:maxlen]
