"""Command-line entry point for phone-rescue."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from phonerescue import __version__

BANNER = """\
phone-rescue {ver} - consent-based backup & recovery for a phone you own
----------------------------------------------------------------------
Only use this on a device you own or are expressly authorised to access.
The phone must be connected by cable, unlocked, and you must approve the
connection on the phone itself. Nothing is uploaded; data is saved locally.
"""


def _ios(args) -> int:
    from phonerescue.common.report import write_report
    from phonerescue.ios import backup as backup_mod
    from phonerescue.ios import connect as conn
    from phonerescue.ios import extract as extract_mod
    from phonerescue.ios import media as media_mod
    from phonerescue.ios import photos as photos_mod

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sections: list[str] = []

    async def run() -> dict:
        try:
            lockdown = await conn.connect()
        except (conn.NoDeviceError, conn.NotTrustedError) as e:
            print(f"\n{e}\n", file=sys.stderr)
            raise SystemExit(2)
        info = await conn.device_info(lockdown)
        print(f"Connected: {info['name']}  ({info['model']}, iOS {info['os']})\n")

        print("[1/4] Camera roll")
        m = await media_mod.pull_camera_roll(lockdown, out)
        sections.append(f"Camera roll: {m['count']} files")

        if args.recover_deleted:
            print("\n[2/4] Deleted photos")
            r = await photos_mod.recover(lockdown, out)
            sections.extend([f"Recently Deleted (full quality): {r.get('trashed', 0)}",
                             f"Permanently deleted thumbnails: {r.get('thumbnails', 0)}"])

        if args.backup:
            print("\n[3/4] Full backup")
            backup_dir = await backup_mod.full_backup(lockdown, out)
            print("\n[4/4] Extracting messages / contacts / calls / locations")
            sections.extend(extract_mod.extract_all(backup_dir, out))
        return info

    info = asyncio.run(run())
    write_report(out, {"name": info["name"], "model": info["model"],
                       "os": info["os"], "serial": info["serial"]}, sections)
    print(f"\nDone. Everything saved under: {out}")
    print(f"See {out / 'REPORT.txt'}")
    return 0


def _android(args) -> int:
    from phonerescue.android import connect as conn
    from phonerescue.android import extract as extract_mod
    from phonerescue.common.report import write_report

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    try:
        adb = conn.find_adb()
        serial = conn.check_device(adb)
    except conn.AdbError as e:
        print(f"\n{e}\n", file=sys.stderr)
        return 2

    model = conn.run(adb, "shell", "getprop", "ro.product.model").strip()
    osver = conn.run(adb, "shell", "getprop", "ro.build.version.release").strip()
    print(f"Connected: {model}  (Android {osver}, serial {serial})\n")

    sections = extract_mod.export_all(adb, out)
    write_report(out, {"name": model, "model": model, "os": f"Android {osver}",
                       "serial": serial}, sections)
    print(f"\nDone. Everything saved under: {out}")
    print(f"See {out / 'REPORT.txt'}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="phonerescue",
        description="Consent-based backup & recovery for a phone you own.",
    )
    parser.add_argument("--version", action="version", version=f"phone-rescue {__version__}")
    sub = parser.add_subparsers(dest="platform", required=True)

    pi = sub.add_parser("ios", help="iPhone / iPad")
    pi.add_argument("--out", required=True, help="output folder")
    pi.add_argument("--recover-deleted", action="store_true",
                    help="also recover Recently Deleted + permanently-deleted thumbnails")
    pi.add_argument("--backup", action="store_true",
                    help="also make a full backup and export messages/contacts/calls/locations")
    pi.set_defaults(func=_ios)

    pa = sub.add_parser("android", help="Android")
    pa.add_argument("--out", required=True, help="output folder")
    pa.set_defaults(func=_android)

    args = parser.parse_args(argv)
    print(BANNER.format(ver=__version__))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
