"""Select a contract on warm-up activity and save a clock-time depth profile."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from fetch import DATES, ROOT, STORE
from replay import COLS, US, prepare


def main():
    day = DATES[-1]
    start = pd.Timestamp(day, tz="UTC").value // 1000
    raw = pd.read_csv(STORE / (day+".csv.gz"),usecols=COLS)
    warmup = raw[raw.local_timestamp < start + 60*US]
    symbol = warmup.groupby("symbol").size().sort_values(ascending=False,kind="stable").index[0]
    raw = raw[raw.symbol == symbol].sort_values("local_timestamp",kind="stable").drop_duplicates(
        "local_timestamp",keep="last")
    valid = prepare(raw).valid.to_numpy()
    stamp = raw.local_timestamp.to_numpy()
    seconds = np.arange(60,1200,2)
    saved = []
    fields = [f"bids[{i}].amount" for i in reversed(range(5))]+[f"asks[{i}].amount" for i in range(5)]
    sizes = raw[fields].fillna(0).to_numpy()
    for sec in seconds:
        now = start + int(sec)*US
        i = np.searchsorted(stamp, now, side="right")-1
        if i < 0 or not valid[i] or now-raw.timestamp.iloc[i]>2*US:
            saved.append(None)
        else:
            saved.append(sizes[i].tolist())
    (ROOT/"results/replay/heatmap.json").write_text(json.dumps(dict(date=day,symbol=symbol,
            seconds=seconds.tolist(), ranks=["Bid 5","Bid 4","Bid 3","Bid 2","Bid 1",
                                           "Ask 1","Ask 2","Ask 3","Ask 4","Ask 5"],
            size_units="BTC", sizes=saved))+"\n")


if __name__ == "__main__":
    main()
