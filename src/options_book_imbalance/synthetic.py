"""Deterministic fixture solely for testing the pipeline, never market evidence."""
from __future__ import annotations

import json
import random
from pathlib import Path


def make_fixture(path: Path, seed: int = 7, messages: int = 501) -> dict:
    rng = random.Random(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    mid_tick = 1000
    prior_imbalance = 0
    with path.open("w") as sink:
        sink.write(json.dumps({"type": "metadata", "source": "synthetic_fixture",
                               "seed": seed, "messages": messages,
                               "warning": "Generated data; not exchange observations"}) + "\n")
        for i in range(messages):
            if i:
                aligned = rng.random() < .75
                mid_tick += prior_imbalance if aligned else -prior_imbalance
            new_imbalance = rng.choice([-1, 1])
            bid_size, ask_size = (8.0, 2.0) if new_imbalance > 0 else (2.0, 8.0)
            bid_price = round((mid_tick - 1) * .0001, 7)
            ask_price = round((mid_tick + 1) * .0001, 7)
            if i == 0:
                event = {"type": "snapshot", "bids": [["new", bid_price, bid_size]],
                         "asks": [["new", ask_price, ask_size]]}
            else:
                event = {"type": "change", "prev_change_id": i,
                         "bids": [["delete", old_bid, 0], ["new", bid_price, bid_size]],
                         "asks": [["delete", old_ask, 0], ["new", ask_price, ask_size]]}
            event.update({"timestamp": 1800000000000 + i*100, "change_id": i+1})
            sink.write(json.dumps(event) + "\n")
            old_bid, old_ask = bid_price, ask_price
            prior_imbalance = new_imbalance
    return {"path": str(path), "seed": seed, "messages": messages,
            "source": "synthetic_fixture"}
