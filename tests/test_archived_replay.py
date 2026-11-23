"""Regression cases for event order, censoring and cost signs in archive mode."""
from collections import Counter
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "archive"))
from replay import US, COLS, EVENT_COLUMNS, prepare, label_contract, fixed_horizon_counts
from study import economics
from peer_control import pressure


def raw(time, bid=1., ask=1.2, bid_size=3., ask_size=1., delay=0):
    row = dict.fromkeys(COLS, np.nan)
    row.update(symbol="BTC-1JAN25-50000-C", local_timestamp=int(time*US),
               timestamp=int(time*US)-delay)
    row.update({"bids[0].price": bid, "asks[0].price": ask,
                "bids[0].amount": bid_size, "asks[0].amount": ask_size})
    return row


def run(rows):
    books = prepare(pd.DataFrame(rows))
    counts = Counter()
    events = label_contract("BTC-1JAN25-50000-C", books, 0, 1200*US, counts)
    return pd.DataFrame(events, columns=EVENT_COLUMNS), counts


class ArchivedReplayTests(unittest.TestCase):
    def test_first_move_and_causal_features(self):
        # First decision uses the already observed down move; its label arrives later.
        rows = [raw(59, 1.01), raw(60), raw(60.2), raw(60.4, 1.05, bid_size=1, ask_size=9)]
        events, counts = run(rows)
        self.assertEqual(counts["moved"], 1)
        self.assertEqual(events.outcome_us[0], 60400000)
        self.assertEqual(events.previous_direction[0], -1)
        self.assertEqual(events.l5[0], .5)
        self.assertEqual(events.up[0], 1)

    def test_ties_do_not_create_observable_move(self):
        events, counts = run([raw(60),raw(60.5,1.1),raw(60.5),raw(61,.98)])
        self.assertEqual((len(events), events.up[0]), (1, 0))
        self.assertEqual(counts["decisions"], 2)

    def test_timeout_and_invalid_barrier(self):
        events, counts = run([raw(60),raw(71,1.1),raw(72,delay=3*US),raw(75,.94)])
        self.assertEqual(len(events), 0)
        self.assertEqual((counts["timeout"],counts["invalidated"],counts["no_later_quote"]), (1,1,1))
        exactly, _ = run([raw(60),raw(70,1.01)])
        self.assertEqual(len(exactly),1)

    def test_moving_quote_does_not_cross_contract_or_final_cutoff(self):
        rows = [raw(60),raw(1195,1.1)]
        second = raw(61,1.1)
        second["symbol"] = "BTC-1JAN25-51000-C"
        table = prepare(pd.DataFrame(rows+[second]))
        counts = Counter()
        out = [r for sym,group in table.groupby("symbol")
               for r in label_contract(sym,group,0,1200*US,counts)]
        self.assertEqual(out, [])
        self.assertEqual(counts["decisions"],2)

    def test_fixed_clock_uses_first_quote_at_or_after_horizon(self):
        table = prepare(pd.DataFrame([raw(60),raw(60.5,.9),raw(61.1,1.04),raw(62.1,1.04)]))
        c = fixed_horizon_counts(table,0,1200*US)
        self.assertEqual((c["scored"],c["up"],c["correct"],c["unchanged"]),(1,1,1,1))
        table = prepare(pd.DataFrame([raw(60),raw(60.5,delay=3*US),raw(61.1,.9)]))
        self.assertEqual(fixed_horizon_counts(table,0,1200*US)["scored"],0)

    def test_peer_signal_excludes_self_current_second_and_reverses_puts(self):
        items = []
        for symbol, second_bid in [("BTC-A-C",1.06),("BTC-B-P",.98)]:
            for t,b in [(60,1.),(61.3,second_bid),(62.01,.8)]:
                r = raw(t,b)
                r["symbol"] = symbol
                items.append(r)
        events = pd.DataFrame(dict(symbol=["BTC-A-C","BTC-B-P","BTC-A-C"],
                                   decision_us=[62*US,62*US,61*US],is_put=[0,1,0]))
        self.assertEqual(pressure(prepare(pd.DataFrame(items)),events).tolist(),[1.,-1.,0.])

    def test_spread_cost_both_directions(self):
        sample = pd.DataFrame(dict(entry_bid=[100,100],entry_ask=[102,102],
                                   exit_bid=[101,98],exit_ask=[103,100],p=[.9,.1]))
        self.assertAlmostEqual(economics(sample,"p")["mean_mid_spreads"], .75)
        self.assertAlmostEqual(economics(sample,"p")["mean_crossed_spreads"], -.25)


if __name__ == "__main__":
    unittest.main()
