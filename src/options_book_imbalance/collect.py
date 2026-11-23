"""Public Deribit options feed recorder. No account or order endpoint is used."""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from .core import Book

REST = "https://www.deribit.com/api/v2/public/"
WS = "wss://www.deribit.com/ws/api/v2"


def discover(currency: str = "BTC", limit: int = 10) -> list[dict]:
    """One instrument request and one chain-summary request; avoid polling."""
    def get(method: str, params: dict) -> list[dict]:
        url = REST + method + "?" + urlencode(params)
        with urlopen(url, timeout=20) as response:
            payload = json.load(response)
        if "error" in payload:
            raise RuntimeError(payload["error"])
        return payload["result"]

    instruments = get("get_instruments", {"currency": currency, "kind": "option", "expired": "false"})
    summary = get("get_book_summary_by_currency", {"currency": currency, "kind": "option"})
    by_name = {x["instrument_name"]: x for x in instruments}
    now_ms = int(time.time() * 1000)
    candidates = []
    for row in summary:
        instrument = by_name.get(row.get("instrument_name"))
        if not instrument or not instrument.get("is_active", True):
            continue
        if instrument.get("expiration_timestamp", 0) <= now_ms + 24*3600*1000:
            continue
        if not row.get("bid_price") or not row.get("ask_price"):
            continue
        candidates.append({"instrument_name": row["instrument_name"],
                           "volume": row.get("volume") or 0,
                           "bid_price": row["bid_price"], "ask_price": row["ask_price"],
                           "expiration_timestamp": instrument["expiration_timestamp"],
                           "strike": instrument.get("strike"), "option_type": instrument.get("option_type")})
    return sorted(candidates, key=lambda r: float(r["volume"]), reverse=True)[:limit]


def collect(instrument: str, seconds: int, output: Path, append: bool = False) -> dict:
    import websocket

    if seconds <= 0:
        raise ValueError("seconds must be positive")
    channel = f"book.{instrument}.100ms"
    deadline = time.monotonic() + seconds
    counts = {"messages": 0, "gaps": 0, "reconnects": 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    existing = append and output.exists() and output.stat().st_size > 0
    with output.open("a" if append else "w") as sink:
        sink.write(json.dumps({"type": "capture_resume" if existing else "metadata",
                               "instrument": instrument, "channel": channel,
                               "venue": "Deribit",
                               "capture_started_unix_ms": int(time.time()*1000)}) + "\n")
        while time.monotonic() < deadline:
            book = Book()
            ws = None
            try:
                ws = websocket.create_connection(WS, timeout=20)
                ws.send(json.dumps({"jsonrpc": "2.0", "id": 1,
                                    "method": "public/subscribe",
                                    "params": {"channels": [channel]}}))
                while time.monotonic() < deadline:
                    ws.settimeout(min(5, max(.1, deadline-time.monotonic())))
                    try:
                        raw = ws.recv()
                        if not raw:
                            raise websocket.WebSocketConnectionClosedException("empty close frame")
                        message = json.loads(raw)
                    except websocket.WebSocketTimeoutException:
                        continue
                    if message.get("id") == 1 and "error" in message:
                        raise RuntimeError(message["error"])
                    if message.get("method") != "subscription":
                        continue
                    params = message.get("params", {})
                    if params.get("channel") != channel:
                        continue
                    event = params["data"]
                    event["type"] = event.get("type") or (
                        "change" if "prev_change_id" in event else "snapshot")
                    sink.write(json.dumps(event, separators=(",", ":")) + "\n")
                    sink.flush()
                    counts["messages"] += 1
                    if not book.apply(event):
                        counts["gaps"] += 1
                        break  # reconnect for a fresh full snapshot
            except (OSError, TimeoutError, websocket.WebSocketException,
                    json.JSONDecodeError) as exc:
                counts["reconnects"] += 1
                sink.write(json.dumps({"type": "connection_error", "detail": str(exc),
                                       "timestamp": int(time.time()*1000)}) + "\n")
                sink.flush()
            finally:
                if ws is not None:
                    ws.close()
            if time.monotonic() < deadline:
                time.sleep(1)
    return {"output": str(output), **counts}
