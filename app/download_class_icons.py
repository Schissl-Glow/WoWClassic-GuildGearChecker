# -*- coding: utf-8 -*-
"""Downloads and caches the nine WoW class icons used by Guild Gear Checker.
Source: Wowhead/Zamimg. Existing icons are kept unless --force is supplied.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import os
import sys
import urllib.request
from pathlib import Path
from io import BytesIO
try:
    from PIL import Image
except Exception:
    Image = None

HERE = Path(__file__).resolve().parent
BASE = HERE.parent if HERE.name.casefold() == "app" else HERE
OUT = BASE / "assets" / "classes"
CLASSES = ["Druid", "Hunter", "Mage", "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Warrior"]
ICON_IDS = {
    "Druid": 625999, "Hunter": 626000, "Mage": 626001, "Paladin": 626003,
    "Priest": 626004, "Rogue": 626005, "Shaman": 626006, "Warlock": 626007, "Warrior": 626008,
}
URLS = {c: f"https://wow.zamimg.com/images/wow/icons/large/classicon_{c.lower()}.jpg" for c in CLASSES}


def valid_bytes(data: bytes) -> bool:
    if len(data) < 300 or not data.startswith(b"\xff\xd8"):
        return False
    if Image is not None:
        try:
            with Image.open(BytesIO(data)) as im:
                im.verify()
            with Image.open(BytesIO(data)) as im:
                return im.width >= 32 and im.height >= 32
        except Exception:
            return False
    return True


def valid_cached(path: Path) -> bool:
    try:
        return valid_bytes(path.read_bytes())
    except OSError:
        return False


def fetch_one(cls: str, force: bool, timeout: int) -> tuple[str, str]:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{cls.lower()}.jpg"
    if not force and valid_cached(target):
        return cls, "cached"
    tmp = target.with_suffix(".jpg.tmp")
    last_exc = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(URLS[cls], headers={
                "User-Agent": "Mozilla/5.0 GuildGearChecker/0.5",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                "Cache-Control": "no-cache",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read(1024 * 1024)
            if not valid_bytes(data):
                raise ValueError("response is not a valid class icon JPEG")
            tmp.write_bytes(data)
            os.replace(tmp, target)
            return cls, "downloaded" if attempt == 1 else f"downloaded (retry {attempt})"
        except Exception as exc:
            last_exc = exc
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            if attempt < 3:
                import time
                time.sleep(0.6 * attempt)
    return cls, f"ERROR after 3 attempts: {last_exc}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--timeout", type=int, default=10)
    args = ap.parse_args()
    print("WoW Class-Icons ->", OUT)
    print("Source: Wowhead / wow.zamimg.com")
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(fetch_one, c, args.force, max(2, args.timeout)) for c in CLASSES]
        for fut in concurrent.futures.as_completed(futures):
            cls, status = fut.result()
            print(f"{cls:10s} {status}")
            if status.startswith("ERROR"):
                failures += 1
    if failures:
        print(f"\n{failures} Icon(s) konnten nicht geladen werden.")
        print("Der Gear Checker nutzt dafuer die mitgelieferten Offline-Fallback-Icons.")
        return 1
    print("\nAlle 9 Class-Icons sind lokal gespeichert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
