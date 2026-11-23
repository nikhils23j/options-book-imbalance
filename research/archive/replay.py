"""Label non-overlapping, contract-specific next-mid moves in normalized snapshots."""
from __future__ import annotations
from collections import Counter
import numpy as np
import pandas as pd

US = 1_000_000
HORIZON = 10 * US
PRICE_SCALE = 100_000_000
COLS = ["symbol", "local_timestamp", "timestamp"] + [
    f"{s}[{n}].{f}" for n in range(5) for s in ["bids", "asks"] for f in ["price", "amount"]
]
FEATURES = ["previous_direction", "log_relative_spread", "is_put", "l1", "l5"]
EVENT_COLUMNS = ["symbol", "decision_us", "outcome_us", *FEATURES, "up",
                 "entry_bid", "entry_ask", "exit_bid", "exit_ask"]


def prepare(raw):
    # Keep the last observable state if several updates have the same receipt time.
    unique = raw.sort_values("local_timestamp", kind="stable").drop_duplicates(
        ["symbol", "local_timestamp"], keep="last").copy()
    valid = unique.local_timestamp.sub(unique.timestamp).between(0, 2 * US).to_numpy()
    sizes = {}
    for side in ("bids", "asks"):
        price = unique[[f"{side}[{i}].price" for i in range(5)]].to_numpy(float)
        amount = unique[[f"{side}[{i}].amount" for i in range(5)]].to_numpy(float)
        present = np.isfinite(price) & np.isfinite(amount) & (price > 0) & (amount > 0)
        missing = np.isnan(price) & np.isnan(amount)
        valid &= present[:, 0] & (present | missing).all(axis=1)
        valid &= ~(present[:, 1:] & ~present[:, :-1]).any(axis=1)
        differences = np.diff(price, axis=1)
        valid &= ~((differences >= 0 if side == "bids" else differences <= 0) &
                   present[:, 1:]).any(axis=1)
        sizes[side] = (amount[:, 0], np.nansum(amount, axis=1))
    bid = unique["bids[0].price"].to_numpy()
    ask = unique["asks[0].price"].to_numpy()
    valid &= bid < ask
    table = unique[["symbol", "local_timestamp"]].copy()
    table["valid"] = valid
    # Represent BTC premiums in satoshis so unchanged mids compare exactly.
    for side, values in [("bid", bid), ("ask", ask)]:
        table[side] = np.rint(np.where(valid, values, 0) * PRICE_SCALE).astype("int64")
    for index, name in enumerate(("l1", "l5")):
        b, a = sizes["bids"][index], sizes["asks"][index]
        table[name] = np.divide(b-a, b+a, out=np.zeros_like(b), where=valid & (b+a > 0))
    with np.errstate(invalid="ignore", divide="ignore"):
        table["log_relative_spread"] = np.where(valid, np.log(2*(ask-bid)/(ask+bid)), 0)
    return table


def label_contract(symbol, group, start_us, end_us, counts):
    """One outstanding prediction per contract. An invalid book resets history."""
    history = None
    previous_direction = 0
    entry = None
    last_start = -US
    labeled = []
    is_put = int(symbol.endswith("-P"))
    fields = ["local_timestamp", "valid", "bid", "ask", "l1", "l5", "log_relative_spread"]
    for now, valid, bid, ask, l1, l5, log_spread in group[fields].itertuples(index=False, name=None):
        if entry is not None and now > entry[0] + HORIZON:
            counts["timeout"] += 1
            entry = None
        if not valid:
            if entry is not None:
                counts["invalidated"] += 1
            entry, history, previous_direction = None, None, 0
            continue
        mid2 = bid + ask
        if history is not None and history != mid2:
            previous_direction = 1 if mid2 > history else -1
        history = mid2
        if entry is not None and mid2 != entry[1] + entry[2]:
            t, b, a, prev, spread, i1, i5 = entry
            labeled.append((symbol, t, now, prev, spread, is_put, i1, i5, int(mid2 > b+a),
                            b, a, bid, ask))
            counts["moved"] += 1
            entry = None
        if entry is None and start_us + 60*US <= now < end_us - HORIZON and now-last_start >= US:
            entry = (now, bid, ask, previous_direction, log_spread, l1, l5)
            last_start = now
            counts["decisions"] += 1
    if entry is not None:
        counts["no_later_quote"] += 1
    return labeled


def day_events(path, day):
    raw = pd.read_csv(path, usecols=COLS)
    counts = Counter(raw_snapshots=len(raw), raw_contracts=raw.symbol.nunique())
    prepared = prepare(raw)
    counts["tied_rows_collapsed"] = len(raw) - len(prepared)
    counts["invalid_rows"] = int((~prepared.valid).sum())
    start = pd.Timestamp(day, tz="UTC").value // 1000
    rows = []
    fixed = Counter()
    for symbol, group in prepared.groupby("symbol", sort=False):
        fixed.update(fixed_horizon_counts(group, start, start+1200*US))
        rows.extend(label_contract(symbol, group, start, start+1200*US, counts))
    assert counts["decisions"] == sum(counts[k] for k in ("moved", "timeout", "invalidated", "no_later_quote"))
    events = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    counts["labeled_contracts"] = events.symbol.nunique()
    events.insert(0, "date", day)
    return events, dict(counts), dict(fixed)


def fixed_horizon_counts(group, start, end):
    """Vectorized future lookup with the live pilot's one-second decision clock."""
    clock = group.local_timestamp.to_numpy()
    future = np.searchsorted(clock, clock + US)
    valid = group.valid.to_numpy()
    segment = (~valid).cumsum()
    mid2 = (group.bid + group.ask).to_numpy()
    pressure = group.l5.to_numpy()
    counts = Counter()
    last_decision = -US
    for i in np.flatnonzero(valid & (clock >= start + 60*US) & (clock < end-2*US)):
        if clock[i] - last_decision < US:
            continue
        last_decision = clock[i]
        counts["decision_times"] += 1
        j = future[i]
        if j >= len(group) or clock[j] > clock[i] + 2*US or segment[i] != segment[j]:
            counts["missing_or_invalid"] += 1
            continue
        if mid2[j] == mid2[i]:
            counts["unchanged"] += 1
            continue
        up = bool(mid2[j] > mid2[i])
        counts["nonzero_moves"] += 1
        if pressure[i] == 0:
            counts["abstained"] += 1
            continue
        counts["scored"] += 1
        counts["up"] += up
        counts["correct"] += bool(pressure[i] > 0) == up
    return counts
