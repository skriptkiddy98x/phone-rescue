# phone-rescue

**Consent-based backup & recovery toolkit for a phone you own and physically control.**

`phone-rescue` runs on your computer and exports the data from *your own* iPhone or
Android phone — photos and videos (including items still in the Recently Deleted
trash), messages, contacts, call history, chat attachments and, where the phone
exposes it, location history. It is built for the everyday jobs of *"I deleted a
photo and the 30-day trash hasn't purged it yet"*, *"I'm moving to a new phone and
want a local copy of everything"*, and *"I need a readable export of my own data"*.

It uses only the official, documented device channels (Apple's `usbmux`/AFC and
`mobilebackup2`, Google's `adb`). That means it **cannot** run secretly and it
**cannot** bypass a lock screen:

- the phone must be **physically connected by cable**,
- it must be **unlocked**, and
- you must **actively approve the connection** on the phone itself
  — *Trust This Computer* + passcode on iPhone, *Allow USB debugging* on Android.

There is no stealth mode, no remote capture, and the tool never uploads your data
anywhere — everything is written to a local folder you choose.

## This is not spyware — please read

This tool is for **your own device, or a device whose owner is standing next to you
and has agreed**. Extracting data from someone else's phone without their knowledge
and consent is illegal in most countries and is exactly what this project refuses to
make easy: it needs the owner to unlock and to tap *Trust* / *Allow* every time.

Do **not** use it to monitor a partner, child, employee or anyone else covertly.
If that is the goal, this is the wrong tool and you should stop here.

It sits in the same family as well-known open-source projects such as
[libimobiledevice](https://libimobiledevice.org/),
[iLEAPP/ALEAPP](https://github.com/abrignoni) and the
[Mobile Verification Toolkit](https://github.com/mvt-project/mvt): a consent-based,
local, auditable export — not a surveillance implant.

## What it recovers

### iPhone (iOS)
- **Camera roll** — all photos and videos over AFC, with an inventory.
- **Recently Deleted** — originals of items still in the 30-day trash, in full quality.
- **Permanently deleted** — small thumbnails that iOS leaves behind in its thumbnail
  tables after a photo is gone (decoded from the Apple ASTC format), plus filenames
  left in the photo database. Full-resolution permanently-deleted photos cannot be
  recovered from the device — iOS destroys each file's encryption key on deletion.
- **Full logical backup** (`--backup`) via `mobilebackup2`, then a readable export of:
  Messages (iMessage/SMS) + attachments, contacts, call history, and best-effort
  location history (`routined` / `knowledgeC`) when present in the backup.

### Android
- Media from `DCIM`, `Pictures`, `Movies`, `Download` and app media folders (e.g. WhatsApp).
- Contacts, SMS/MMS and call log via the system content providers (`adb shell content query`).
- App-private storage requires a rooted device; the tool detects root and uses it only if present.

## Requirements
- Python 3.10+
- **iPhone:** Apple's device driver. On Windows the simplest way is the free
  *Apple Devices* app from the Microsoft Store (it ships the `usbmuxd` service).
- **Android:** Google *platform-tools* (`adb`) on your `PATH`, and *USB debugging*
  enabled on the phone.

```bash
pip install -r requirements.txt
```

## Usage

```bash
# iPhone: camera roll + recover the Recently Deleted trash + deleted-photo thumbnails
python -m phonerescue ios --out ./export --recover-deleted

# iPhone: the lot — also a full backup, then export messages/contacts/calls/locations
python -m phonerescue ios --out ./export --recover-deleted --backup

# Android: media + contacts + SMS + call log
python -m phonerescue android --out ./export
```

Every run writes a `REPORT.txt` and a `manifest.csv` (SHA-256 of every file) into the
output folder.

## Legal
You are responsible for using this tool lawfully. Only run it against a device you own
or are expressly authorised to access. The authors provide it for personal backup,
data recovery and lawful forensic use, and accept no liability for misuse. See
[LICENSE](LICENSE).
