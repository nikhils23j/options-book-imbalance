"""Render figures only from a saved analysis JSON; never type result numbers here."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()
    result = json.loads(args.input.read_text())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    label = "SYNTHETIC FIXTURE" if result["capture_metadata"].get("source") == "synthetic_fixture" else "RECORDED EXCHANGE DATA"

    buckets = result.get("buckets", [])
    if buckets:
        fig, ax = plt.subplots(figsize=(7.2, 3.6))
        x = [(b["range"][0]+b["range"][1])/2 for b in buckets]
        y = [b["up_rate"] if b["up_rate"] is not None else float("nan") for b in buckets]
        ax.plot(x, y, marker="o", color="#2563eb")
        for xi, yi, b in zip(x, y, buckets):
            if b["n"] and yi == yi:
                ax.annotate(f'n={b["n"]}', (xi, yi), xytext=(0, 8),
                            textcoords="offset points", ha="center", fontsize=8)
        ax.axhline(.5, color="gray", linestyle="--", linewidth=1)
        ax.set(xlabel="Top-level book imbalance", ylabel="Held-out next-move up rate",
               title=f"Imbalance buckets • {label}", xlim=(-1, 1), ylim=(0, 1))
        fig.tight_layout()
        fig.savefig(args.output_dir / "imbalance_outcomes.png", dpi=160)
        plt.close(fig)

    rows = result.get("sample_rows", [])
    if rows:
        width = max(len(r["bids"]) + len(r["asks"]) for r in rows)
        depth = []
        for r in rows:
            bids = [amount for _, amount in reversed(r["bids"])]
            asks = [amount for _, amount in r["asks"]]
            depth.append(bids + asks + [float("nan")] * (width-len(bids)-len(asks)))
        fig, ax = plt.subplots(figsize=(8, 3.8))
        im = ax.imshow(list(map(list, zip(*depth))), aspect="auto", interpolation="nearest",
                       origin="lower", cmap="magma")
        ax.set(xlabel="Sampled book update", ylabel="Bid depth → ask depth",
               title=f"Liquidity by book level • {label}")
        fig.colorbar(im, ax=ax, label="Size (underlying units)")
        fig.tight_layout()
        fig.savefig(args.output_dir / "liquidity_heatmap.png", dpi=160)
        plt.close(fig)
    print(args.output_dir)


if __name__ == "__main__":
    main()
