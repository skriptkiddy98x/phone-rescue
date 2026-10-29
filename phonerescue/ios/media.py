"""Copy the camera roll (photos + videos) off the iPhone over AFC, with an inventory."""
from __future__ import annotations

import csv
import posixpath
from pathlib import Path

from phonerescue.common.util import aw, human

MEDIA_EXT = {".jpg", ".jpeg", ".heic", ".heif", ".png", ".gif", ".webp", ".tif",
             ".dng", ".mov", ".mp4", ".m4v", ".aae"}


async def _afc(lockdown):
    from pymobiledevice3.services.afc import AfcService
    afc = AfcService(lockdown)
    if hasattr(afc, "connect"):
        await aw(afc.connect())
    return afc


async def _walk(afc, root: str):
    """Yield (path, size) for every file under `root`."""
    try:
        names = await aw(afc.listdir(root))
    except Exception:  # noqa: BLE001
        return
    for name in names:
        if name in (".", ".."):
            continue
        path = posixpath.join(root, name)
        try:
            st = await aw(afc.stat(path))
        except Exception:  # noqa: BLE001
            continue
        if st.get("st_ifmt") == "S_IFDIR":
            async for item in _walk(afc, path):
                yield item
        else:
            yield path, int(st.get("st_size", 0))


async def pull_camera_roll(lockdown, out: Path, progress=print) -> dict:
    afc = await _afc(lockdown)
    dest = out / "camera_roll"
    dest.mkdir(parents=True, exist_ok=True)

    files = []
    async for path, size in _walk(afc, "/DCIM"):
        if posixpath.splitext(path)[1].lower() in MEDIA_EXT:
            files.append((path, size))
    total = sum(s for _, s in files)
    progress(f"camera roll: {len(files)} files, {human(total)}")

    rows = []
    done = 0
    for i, (path, size) in enumerate(files, 1):
        rel = path[len("/DCIM/"):]
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = await aw(afc.get_file_contents(path))
            target.write_bytes(data)
            done += 1
        except Exception as e:  # noqa: BLE001
            rows.append({"file": rel, "size": size, "status": f"error: {e}"})
            continue
        rows.append({"file": rel, "size": size, "status": "ok"})
        if i % 100 == 0 or i == len(files):
            progress(f"  {i}/{len(files)} copied")

    with open(dest / "inventory.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "size", "status"])
        w.writeheader()
        w.writerows(rows)
    return {"count": done, "bytes": total}
