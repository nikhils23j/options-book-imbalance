"""Save canonical UTC slices of public Deribit book snapshots. Run from repo root."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "data" / "replay"
WINDOW = 20 * 60
DATES = [f"{year}-{month:02}-01" for year in (2024, 2025) for month in range(1, 13)
         if (year, month) <= (2025, 11)]


def checksum(path):
    h = hashlib.sha256()
    with gzip.open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def retrieve(day, pinned):
    path = STORE / (day + ".csv.gz")
    url = f"https://datasets.tardis.dev/v1/deribit/book_snapshot_5/{day.replace('-', '/')}/OPTIONS.csv.gz"
    if path.exists() and pinned and checksum(path) == pinned["sha256_csv"]:
        return day, pinned
    start = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()) * 1_000_000
    stop = start + WINDOW * 1_000_000
    part = path.with_suffix(".part")
    for attempt in range(3):
        try:
            with requests.get(url, stream=True, timeout=(20, 60)) as res:
                if res.status_code == 429:
                    raise RuntimeError(f"Provider limit on {day}: {res.text[:250]}. Use the cached release or retry after the provider resets.")
                res.raise_for_status()
                with gzip.GzipFile(fileobj=res.raw) as src, gzip.open(part, "wb", compresslevel=2) as dst:
                    header = src.readline()
                    if not header.startswith(b"exchange,symbol,timestamp,local_timestamp,"):
                        raise ValueError("unexpected source schema")
                    dst.write(header)
                    kept = 0
                    for line in src:
                        _, symbol, _, stamp, _ = line.split(b",", 4)
                        local = int(stamp)
                        if local >= stop:
                            break
                        if local >= start and symbol.startswith(b"BTC-") and symbol.endswith((b"-C", b"-P")):
                            dst.write(line)
                            kept += 1
                    else:
                        raise ValueError(f"archive ended before cutoff on {day}")
            if kept == 0:
                raise ValueError(f"empty BTC slice on {day}")
            digest = checksum(part)
            if pinned and pinned["sha256_csv"] != digest:
                raise ValueError(f"source changed for {day}")
            part.replace(path)
            print(day, kept, flush=True)
            return day, dict(url=url, sha256_csv=digest, rows=kept, seconds=WINDOW)
        except (requests.RequestException, OSError, EOFError) as exc:
            if attempt == 2:
                raise
            print(day, type(exc).__name__, "retry", flush=True)
            time.sleep(2**attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    STORE.mkdir(parents=True, exist_ok=True)
    manifest = STORE / "manifest.json"
    pinned = json.loads(manifest.read_text()) if manifest.exists() else {}
    if args.offline:
        if set(pinned) != set(DATES):
            raise ValueError("manifest incomplete")
        for day in DATES:
            if checksum(STORE / (day + ".csv.gz")) != pinned[day]["sha256_csv"]:
                raise ValueError(f"bad checksum: {day}")
        print(f"Verified {len(DATES)} archived slices")
        return
    with ThreadPoolExecutor(max_workers=3) as pool:
        for day, record in pool.map(lambda d: retrieve(d, pinned.get(d)), DATES):
            pinned[day] = record
            manifest.write_text(json.dumps(pinned, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
