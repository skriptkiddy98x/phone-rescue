"""Write a human-readable REPORT.txt and a manifest.csv (SHA-256 of every file)."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from phonerescue.common.util import human, sha256


def write_manifest(out: Path) -> tuple[int, int]:
    """Hash every file under `out` (except the manifest itself). Returns (count, bytes)."""
    rows = []
    total = 0
    for p in sorted(out.rglob("*")):
        if not p.is_file() or p.name in ("manifest.csv", "REPORT.txt"):
            continue
        size = p.stat().st_size
        total += size
        rows.append({
            "file": str(p.relative_to(out)).replace("\\", "/"),
            "size": size,
            "sha256": sha256(p),
        })
    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "size", "sha256"])
        w.writeheader()
        w.writerows(rows)
    return len(rows), total


def write_report(out: Path, device: dict, sections: list[str]) -> None:
    lines = [
        "phone-rescue export report",
        "=" * 60,
        f"Created:  {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Device:   {device.get('name', '?')}",
        f"Model:    {device.get('model', '?')}",
        f"OS:       {device.get('os', '?')}",
        f"Serial:   {device.get('serial', '?')}",
        "",
        "Consent-based export over the official device channel. The device was",
        "connected by cable, unlocked, and the connection approved on the device.",
        "No data left this computer; nothing was written back to the phone.",
        "",
    ]
    lines += sections
    count, total = write_manifest(out)
    lines += [
        "",
        "Integrity",
        "-" * 60,
        f"Files written: {count}",
        f"Total size:    {human(total)}",
        "SHA-256 of every file is in manifest.csv.",
    ]
    (out / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
