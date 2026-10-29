"""Connect to a USB-attached iPhone over the official usbmux/lockdown channel.

This can only succeed when the phone is unlocked and the user has tapped
"Trust This Computer" (which stores a pairing record). There is no way around
that here, by design.
"""
from __future__ import annotations

from phonerescue.common.util import aw


class NoDeviceError(RuntimeError):
    pass


class NotTrustedError(RuntimeError):
    pass


async def connect():
    """Return a connected lockdown client, or raise a friendly error."""
    try:
        from pymobiledevice3.lockdown import create_using_usbmux
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "pymobiledevice3 is not installed. Run: pip install -r requirements.txt"
        ) from e

    no_device = ("No iPhone detected.\n"
                 "  1. Connect the iPhone by cable and unlock it.\n"
                 "  2. On Windows, make sure the Apple Devices app (Microsoft Store) is\n"
                 "     installed so the usbmuxd service is running.\n"
                 "  3. Tap 'Trust This Computer' on the phone and enter the passcode.")
    not_trusted = ("The iPhone is connected but not trusted/unlocked.\n"
                   "  Unlock the phone, tap 'Trust This Computer' and enter the passcode,\n"
                   "  then run the command again.")
    try:
        lockdown = await aw(create_using_usbmux())
    except Exception as e:  # noqa: BLE001 - map any backend error to guidance
        name = type(e).__name__
        msg = str(e).lower()
        if name in ("NoDeviceConnectedError", "ConnectionFailedError") or \
                any(k in msg for k in ("not connected", "no device", "muxexception", "connection refused")):
            raise NoDeviceError(no_device) from e
        if name in ("PairingError", "PasswordRequiredError", "UserDeniedPairingError",
                    "InvalidHostIDError", "PairingDialogResponsePendingError") or \
                any(k in msg for k in ("pair", "trust", "password", "lock", "denied")):
            raise NotTrustedError(not_trusted) from e
        raise
    return lockdown


async def device_info(lockdown) -> dict:
    async def val(key, domain=None):
        try:
            return await aw(lockdown.get_value(domain=domain, key=key))
        except Exception:  # noqa: BLE001
            return None

    return {
        "name": await val("DeviceName"),
        "model": await val("ProductType"),
        "os": await val("ProductVersion"),
        "build": await val("BuildVersion"),
        "serial": await val("SerialNumber"),
        "udid": getattr(lockdown, "udid", None),
    }
