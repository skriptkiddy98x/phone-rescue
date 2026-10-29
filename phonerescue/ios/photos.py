"""Recover deleted photos/videos from the iPhone photo library.

Two things are recoverable without any exploit:

1. Items in the **Recently Deleted** album (ZTRASHEDSTATE = 1 in Photos.sqlite):
   the originals are still on the device for 30 days and are copied in full quality.

2. Items deleted **permanently**: the full files are gone (iOS destroys the per-file
   key), but the small thumbnails iOS keeps in its thumbnail tables (3307/3324/4531
   `.ithmb`, Apple ASTC 4x4) often survive in now-free slots. We decode those and,
   where possible, recover the original filename left in the photo database.
"""
from __future__ import annotations

import csv
import io
import posixpath
import sqlite3
import struct
import uuid
from pathlib import Path

from phonerescue.common.util import aw, cocoa_to_dt, fmt

THUMB_TABLES = ("4531", "3324", "3307")
SLOT_COUNT = 5632


async def _afc(lockdown):
    from pymobiledevice3.services.afc import AfcService
    afc = AfcService(lockdown)
    if hasattr(afc, "connect"):
        await aw(afc.connect())
    return afc


async def _pull(afc, src: str, dst: Path) -> bool:
    try:
        data = await aw(afc.get_file_contents(src))
    except Exception:  # noqa: BLE001
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return True


def _decode_astc_slot(raw: bytes, slot_size: int, i: int):
    """Decode one thumbnail slot -> (PIL.Image, uuid) or (None, uuid/None)."""
    import texture2ddecoder
    from PIL import Image

    s = raw[i * slot_size:(i + 1) * slot_size]
    if not any(s[:-28]):
        return None, None
    uid = str(uuid.UUID(bytes=s[-28:-12])).upper()
    w, h = struct.unpack("<II", s[-12:-4])
    if not (0 < w <= 256 and 0 < h <= 256):
        return None, uid
    bw, bh = -(-w // 4) * 4, -(-h // 4) * 4
    rgba = texture2ddecoder.decode_astc(s[:(bw // 4) * (bh // 4) * 16], bw, bh, 4, 4)
    img = Image.frombytes("RGBA", (bw, bh), rgba, "raw", "BGRA").convert("RGB")
    return img.crop((0, 0, w, h)), uid


async def recover(lockdown, out: Path, progress=print) -> dict:
    afc = await _afc(lockdown)
    work = out / "_photodb"
    work.mkdir(parents=True, exist_ok=True)

    # Pull the photo database (+ WAL) read-only.
    ok = False
    for name in ("Photos.sqlite", "Photos.sqlite-wal", "Photos.sqlite-shm"):
        got = await _pull(afc, f"/PhotoData/{name}", work / name)
        ok = ok or (name == "Photos.sqlite" and got)
    if not ok:
        progress("could not read the photo database (is the phone unlocked?)")
        return {}

    db = sqlite3.connect(work / "Photos.sqlite")

    # ---- 1. Recently Deleted (trash) ----
    trash_dir = out / "recently_deleted"
    rows = []
    try:
        cur = db.execute(
            "select ZDIRECTORY, ZFILENAME, ZKIND, ZDATECREATED, ZTRASHEDDATE "
            "from ZASSET where ZTRASHEDSTATE = 1"
        )
        trashed = cur.fetchall()
    except sqlite3.Error:
        trashed = []
    for directory, filename, kind, created, trashed_at in trashed:
        src = "/" + posixpath.join(directory, filename)
        sub = "videos" if kind == 1 else "photos"
        if await _pull(afc, src, trash_dir / sub / filename):
            rows.append({
                "file": f"{sub}/{filename}",
                "kind": "video" if kind == 1 else "photo",
                "created": fmt(cocoa_to_dt(created)),
                "trashed": fmt(cocoa_to_dt(trashed_at)),
            })
    if rows:
        trash_dir.mkdir(parents=True, exist_ok=True)
        with open(trash_dir / "list.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["file", "kind", "created", "trashed"])
            w.writeheader()
            w.writerows(rows)
    progress(f"recently deleted (full quality): {len(rows)}")

    # ---- 2. Permanently deleted: thumbnails from free slots ----
    used = {r[0] for r in db.execute(
        "select ZTHUMBNAILINDEX from ZASSET where ZTHUMBNAILINDEX is not null")}
    live_uuids = {r[0].upper() for r in db.execute(
        "select ZUUID from ZASSET where ZUUID is not null")}

    tables = {}
    for fmt_id in THUMB_TABLES:
        p = work / f"{fmt_id}.ithmb"
        if await _pull(afc, f"/PhotoData/Thumbnails/{fmt_id}.ithmb", p):
            tables[fmt_id] = p.read_bytes()

    thumb_count = 0
    if "4531" in tables:
        import re
        from PIL import Image  # noqa: F401 (import check)

        db_raw = (work / "Photos.sqlite").read_bytes()
        thumbs_dir = out / "permanently_deleted_thumbnails"
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        raw = tables["4531"]
        slot_size = len(raw) // SLOT_COUNT
        seen = set()
        tlist = []
        sheet_imgs = []
        for i in range(SLOT_COUNT):
            if i in used:
                continue
            img, uid = _decode_astc_slot(raw, slot_size, i)
            if img is None or uid in live_uuids or uid in seen:
                continue
            lo, hi = img.convert("L").getextrema()
            if hi - lo < 8:  # blank slot
                continue
            seen.add(uid)
            thumb_count += 1
            name = f"deleted_{thumb_count:04d}"
            img.save(thumbs_dir / f"{name}.png")
            # original filename sometimes still present near the UUID in the db
            filename = ""
            for m in re.finditer(uid.encode(), db_raw):
                near = re.search(rb"IMG_E?\d{4}\.(HEIC|JPG|JPEG|PNG|MOV|MP4)",
                                 db_raw[max(0, m.start() - 400):m.end() + 400])
                if near:
                    filename = near.group(0).decode()
                    break
            tlist.append({"file": f"{name}.png", "slot": i, "uuid": uid,
                          "width": img.width, "height": img.height,
                          "probable_filename": filename})
            sheet_imgs.append(img)
        if tlist:
            with open(thumbs_dir / "list.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["file", "slot", "uuid", "width",
                                                  "height", "probable_filename"])
                w.writeheader()
                w.writerows(tlist)
            _contact_sheets(sheet_imgs, out / "permanently_deleted_overview")
    progress(f"permanently deleted (thumbnails): {thumb_count}")

    db.close()
    return {"trashed": len(rows), "thumbnails": thumb_count}


def _contact_sheets(images, dest: Path, per_page=100, cell=128):
    from PIL import Image
    if not images:
        return
    dest.mkdir(parents=True, exist_ok=True)
    cols = 10
    for p in range(0, len(images), per_page):
        batch = images[p:p + per_page]
        rows = -(-len(batch) // cols)
        page = Image.new("RGB", (cols * cell, rows * cell), (24, 24, 24))
        for k, im in enumerate(batch):
            x = (k % cols) * cell + (cell - im.width) // 2
            y = (k // cols) * cell + (cell - im.height) // 2
            page.paste(im, (x, y))
        page.save(dest / f"overview_{p + 1:04d}-{p + len(batch):04d}.jpg", quality=90)
