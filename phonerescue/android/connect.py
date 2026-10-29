"""Locate adb and confirm the phone is connected and has authorised this computer."""
from __future__ import annotations

import shutil
import subprocess


class AdbError(RuntimeError):
    pass


def find_adb() -> str:
    adb = shutil.which("adb")
    if adb:
        return adb
    import os
    for guess in (
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        r"C:\platform-tools\adb.exe",
        "/usr/local/bin/adb",
        "/usr/bin/adb",
    ):
        if os.path.exists(guess):
            return guess
    raise AdbError(
        "adb (Android platform-tools) was not found.\n"
        "  Download Google platform-tools and put adb on your PATH:\n"
        "  https://developer.android.com/tools/releases/platform-tools"
    )


def run(adb: str, *args: str, binary: bool = False, timeout: int = 300):
    out = subprocess.run([adb, *args], capture_output=True, timeout=timeout)
    if binary:
        return out.stdout
    return out.stdout.decode("utf-8", "replace")


def check_device(adb: str) -> str:
    """Return the serial of the one authorised device, or raise with guidance."""
    text = run(adb, "devices")
    lines = [ln.split("\t") for ln in text.splitlines()[1:] if ln.strip()]
    if not lines:
        raise AdbError(
            "No Android device detected.\n"
            "  1. Connect the phone by cable and unlock it.\n"
            "  2. Enable Developer options (tap Build number 7x) and turn on USB debugging.\n"
            "  3. Choose 'File transfer' for the USB mode."
        )
    unauth = [s for s, state in lines if state == "unauthorized"]
    if unauth:
        raise AdbError(
            "The phone is connected but has not authorised this computer.\n"
            "  Unlock the phone and tap 'Allow' on the 'Allow USB debugging?' prompt,\n"
            "  then run the command again."
        )
    ready = [s for s, state in lines if state == "device"]
    if not ready:
        raise AdbError(f"Device not ready: {lines}")
    return ready[0]


def is_rooted(adb: str) -> bool:
    try:
        out = run(adb, "shell", "su", "-c", "id", timeout=10)
        return "uid=0" in out
    except Exception:  # noqa: BLE001
        return False
