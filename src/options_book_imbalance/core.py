"""Book reconstruction and a predeclared, chronological signal evaluation."""
from __future__ import annotations

import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Book:
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    change_id: int | None = None
    valid: bool = False
    segment: int = 0

    def apply(self, event: dict) -> bool:
        """Return false on a sequence gap; never use stale state after one."""
        kind = event.get("type")
        if kind == "snapshot":
            self.bids.clear()
            self.asks.clear()
            self.segment += 1
            self.valid = True
        elif kind == "change":
            if not self.valid or event.get("prev_change_id") != self.change_id:
                self.valid = False
                self.bids.clear()
                self.asks.clear()
                return False
        else:
            return False
        for side_name, book in (("bids", self.bids), ("asks", self.asks)):
            for action, raw_price, raw_amount in event.get(side_name, []):
                price, amount = float(raw_price), float(raw_amount)
                if not math.isfinite(price) or not math.isfinite(amount) or price <= 0 or amount < 0:
                    self.valid = False
                    return False
                if action == "delete" or amount == 0:
                    book.pop(price, None)
                elif action in ("new", "change"):
                    book[price] = amount
                else:
                    self.valid = False
                    return False
        self.change_id = int(event["change_id"])
        if self.bids and self.asks and max(self.bids) >= min(self.asks):
            self.valid = False
            return False
        return True

    def observation(self, event: dict, levels: int) -> dict | None:
        if not self.valid or not self.bids or not self.asks:
            return None
        bids = sorted(self.bids.items(), reverse=True)[:levels]
        asks = sorted(self.asks.items())[:levels]
        bid_size = sum(amount for _, amount in bids)
        ask_size = sum(amount for _, amount in asks)
        if bid_size + ask_size <= 0:
            return None
        best_bid, best_ask = bids[0][0], asks[0][0]
        return {
            "ts": int(event["timestamp"]), "segment": self.segment,
            "mid": (best_bid + best_ask) / 2,
            "spread": best_ask - best_bid,
            "imbalance": (bid_size - ask_size) / (bid_size + ask_size),
            "bids": bids, "asks": asks,
        }


def load_observations(path: Path, levels: int = 5) -> tuple[list[dict], dict]:
    book = Book()
    observations: list[dict] = []
    counts = {"messages": 0, "gaps": 0, "invalid": 0, "snapshots": 0}
    with path.open() as source:
        for line in source:
            event = json.loads(line)
            if event.get("type") not in ("snapshot", "change"):
                continue
            counts["messages"] += 1
            if event["type"] == "snapshot":
                counts["snapshots"] += 1
            valid = book.apply(event)
            if not valid:
                counts["gaps" if event.get("type") == "change" and
                       event.get("prev_change_id") != book.change_id else "invalid"] += 1
                continue
            row = book.observation(event, levels)
            if row:
                if observations and row["ts"] < observations[-1]["ts"]:
                    raise ValueError("Non-monotonic timestamps in capture")
                observations.append(row)
    return observations, counts


def labels(observations: list[dict], horizon_ms: int, tolerance_ms: int,
           diagnostics: dict | None = None) -> list[dict]:
    """Take disjoint decision times; label using first same-segment quote after horizon."""
    out = []
    tally = {"decision_times": 0, "no_future": 0, "crossed_segment": 0,
             "future_too_late": 0, "zero_mid_move": 0, "labeled": 0}
    last_decision = -10**30
    j = 0
    for i, row in enumerate(observations):
        if row["ts"] - last_decision < horizon_ms:
            continue
        last_decision = row["ts"]
        tally["decision_times"] += 1
        target = row["ts"] + horizon_ms
        j = max(j, i + 1)
        while j < len(observations) and observations[j]["ts"] < target:
            j += 1
        if j >= len(observations):
            tally["no_future"] += 1
            break
        future = observations[j]
        if future["segment"] != row["segment"]:
            tally["crossed_segment"] += 1
            continue
        if future["ts"] > target + tolerance_ms:
            tally["future_too_late"] += 1
            continue
        move = future["mid"] - row["mid"]
        if move == 0:
            tally["zero_mid_move"] += 1
            continue
        out.append({"ts": row["ts"], "future_ts": future["ts"],
                    "imbalance": row["imbalance"], "spread": row["spread"],
                    "mid": row["mid"], "move": move, "up": int(move > 0)})
        tally["labeled"] += 1
    if diagnostics is not None:
        diagnostics.update(tally)
    return out


def wilson(success: int, count: int) -> list[float] | None:
    if not count:
        return None
    z = 1.96
    p = success / count
    denominator = 1 + z*z/count
    center = (p + z*z/(2*count)) / denominator
    radius = z * math.sqrt(p*(1-p)/count + z*z/(4*count*count)) / denominator
    return [center-radius, center+radius]


def evaluate(rows: list[dict], train_fraction: float = .7) -> dict:
    if len(rows) < 20:
        return {"status": "insufficient_data", "labels": len(rows),
                "reason": "Need at least 20 nonzero, nonoverlapping labeled moves"}
    cut = max(1, min(len(rows)-1, int(len(rows)*train_fraction)))
    train, test = rows[:cut], rows[cut:]
    majority_up = int(sum(r["up"] for r in train) * 2 >= len(train))
    # The zero threshold and sign rule are fixed before examining any labels.
    eligible = [r for r in test if r["imbalance"] != 0]
    correct = sum(int((r["imbalance"] > 0) == bool(r["up"])) for r in eligible)
    baseline = sum(int(r["up"] == majority_up) for r in eligible)
    # Equal-width buckets preserve their interpretation even if a bucket is empty.
    buckets = []
    for lo, hi in [(-1, -.6), (-.6, -.2), (-.2, .2), (.2, .6), (.6, 1.000001)]:
        subset = [r for r in test if lo <= r["imbalance"] < hi]
        buckets.append({"range": [lo, min(hi, 1)], "n": len(subset),
                        "mean_move": statistics.mean(r["move"] for r in subset) if subset else None,
                        "up_rate": statistics.mean(r["up"] for r in subset) if subset else None})
    return {
        "status": "evaluated", "labels": len(rows), "train": len(train), "test": len(test),
        "train_end_ts": train[-1]["ts"], "test_start_ts": test[0]["ts"],
        "evaluated_test": len(eligible), "sign_correct": correct,
        "sign_accuracy": correct/len(eligible) if eligible else None,
        "sign_accuracy_wilson95": wilson(correct, len(eligible)),
        "majority_baseline_accuracy": baseline/len(eligible) if eligible else None,
        "majority_class_from_train": majority_up,
        "buckets": buckets,
    }


def analyze(path: Path, horizon_ms: int = 1000, tolerance_ms: int = 500,
            levels: int = 5) -> dict:
    started = time.perf_counter()
    with path.open() as source:
        first_line = source.readline()
    metadata = json.loads(first_line) if first_line else {}
    if metadata.get("type") != "metadata":
        metadata = {"source": "unknown"}
    observations, counts = load_observations(path, levels)
    label_diagnostics: dict = {}
    rows = labels(observations, horizon_ms, tolerance_ms, label_diagnostics)
    result = evaluate(rows)
    result.update({"source": str(path), "capture_metadata": metadata,
                   "horizon_ms": horizon_ms,
                   "tolerance_ms": tolerance_ms, "levels": levels,
                   "observations": len(observations), "capture_counts": counts,
                   "label_diagnostics": label_diagnostics,
                   "first_ts": observations[0]["ts"] if observations else None,
                   "last_ts": observations[-1]["ts"] if observations else None,
                   "environment": {"python": sys.version.split()[0],
                                   "load_average": list(os.getloadavg())},
                   "run": {"command": " ".join(sys.argv), "repetitions": 1,
                           "elapsed_seconds": time.perf_counter()-started},
                   "sample_rows": [{"ts": r["ts"], "imbalance": r["imbalance"],
                                    "mid": r["mid"], "bids": r["bids"], "asks": r["asks"]}
                                   for r in observations[::max(1, len(observations)//250)]][:250]})
    return result
