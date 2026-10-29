"""Make a full logical backup with the official mobilebackup2 service.

This is the same mechanism Finder/iTunes use. It is written to a local folder only;
nothing is uploaded. The phone will ask for its passcode the first time.
"""
from __future__ import annotations

import time
from pathlib import Path

from phonerescue.common.util import aw


async def full_backup(lockdown, out: Path, progress=print) -> Path:
    from pymobiledevice3.services.mobilebackup2 import Mobilebackup2Service

    backup_dir = out / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    service = Mobilebackup2Service(lockdown)
    try:
        if await aw(service.get_will_encrypt()):
            progress("note: backup encryption is ON for this device; the backup will "
                     "be encrypted with the password you set in Finder/iTunes.")
    except Exception:  # noqa: BLE001
        pass

    last = [0.0, -1]

    def cb(pct):
        p = int(pct)
        if p != last[1] or time.time() - last[0] > 30:
            last[:] = [time.time(), p]
            progress(f"  backup {pct:5.1f}%")

    progress("starting full backup (enter the passcode on the phone if asked)...")
    await aw(service.backup(full=True, backup_directory=backup_dir, progress_callback=cb))
    progress("backup complete")
    return backup_dir
