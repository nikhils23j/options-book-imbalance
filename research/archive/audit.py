"""Independently recompute reported holdout scores from the saved decision ledger."""
import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "results/replay"


def main():
    result = json.loads((ROOT/"summary.json").read_text())
    ends = {}
    totals = defaultdict(Counter)
    with gzip.open(ROOT/"decisions-holdout.csv.gz", "rt") as src:
        for row in csv.DictReader(src):
            key = row["date"], row["symbol"]
            t, end = int(row["decision_us"]), int(row["outcome_us"])
            assert row["date"] >= "2025" and ends.get(key,0) <= t < end <= t + 10_000_000
            ends[key] = end
            b, a, b1, a1 = (int(row[k]) for k in ("entry_bid","entry_ask","exit_bid","exit_ask"))
            up = int(row["up"])
            assert b < a and b1 < a1 and b+a != b1+a1 and up == int(b+a < b1+a1)
            for model in ("baseline", "with_depth"):
                p = float(row[model])
                assert 0 <= p <= 1
                totals[model]["n"] += 1
                totals[model]["hits"] += int((p >= .5) == up)
                totals[model]["sse"] += (p - up)**2
    for name, tally in totals.items():
        expected = result["scores"][name]
        assert tally["n"] == expected["n"] and tally["hits"] == expected["correct"]
        assert math.isclose(tally["sse"]/tally["n"],expected["brier"],abs_tol=1e-11)
    print(f"Verified {totals['with_depth']['n']:,} outcome directions, non-overlapping intervals and paired scores.")


if __name__ == "__main__":
    main()
