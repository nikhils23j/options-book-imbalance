import json
import tempfile
import unittest
from pathlib import Path

from options_book_imbalance.core import Book, analyze, labels, load_observations
from options_book_imbalance.synthetic import make_fixture


class BookTests(unittest.TestCase):
    def test_snapshot_delta_delete_and_gap(self):
        book = Book()
        self.assertTrue(book.apply({"type": "snapshot", "change_id": 1,
                                    "bids": [["new", 10, 2]], "asks": [["new", 12, 3]]}))
        self.assertTrue(book.apply({"type": "change", "prev_change_id": 1, "change_id": 2,
                                    "bids": [["change", 10, 4]], "asks": [["delete", 12, 0], ["new", 13, 1]]}))
        self.assertEqual(book.bids, {10: 4})
        self.assertEqual(book.asks, {13: 1})
        self.assertFalse(book.apply({"type": "change", "prev_change_id": 1, "change_id": 3,
                                     "bids": [], "asks": []}))
        self.assertFalse(book.valid)
        self.assertFalse(book.bids)
        self.assertTrue(book.apply({"type": "snapshot", "change_id": 5,
                                    "bids": [["new", 9, 1]], "asks": [["new", 11, 1]]}))
        self.assertEqual(book.segment, 2)

    def test_labels_never_cross_gap_or_use_early_future(self):
        rows = [
            {"ts": 0, "segment": 1, "mid": 10, "imbalance": .5, "spread": 1},
            {"ts": 50, "segment": 1, "mid": 11, "imbalance": .2, "spread": 1},
            {"ts": 100, "segment": 2, "mid": 12, "imbalance": -.3, "spread": 1},
            {"ts": 200, "segment": 2, "mid": 11, "imbalance": .3, "spread": 1},
        ]
        actual = labels(rows, 100, 0)
        self.assertEqual(len(actual), 1)
        self.assertEqual((actual[0]["ts"], actual[0]["future_ts"]), (100, 200))

    def test_fixture_causal_study(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.jsonl"
            make_fixture(path)
            result = analyze(path, horizon_ms=100, tolerance_ms=0)
            self.assertEqual(result["capture_metadata"]["source"], "synthetic_fixture")
            self.assertEqual(result["capture_counts"]["gaps"], 0)
            self.assertEqual(result["status"], "evaluated")
            self.assertGreater(result["test"], 100)
            self.assertLess(result["train_end_ts"], result["test_start_ts"])
            self.assertGreater(result["sign_accuracy"], .6)


if __name__ == "__main__":
    unittest.main()
