"""Draw the held-out research figure from saved aggregate results."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def main():
    result = json.loads((ROOT / "results/replay/summary.json").read_text())
    dates = list(result["by_date"])
    gain = np.array([result["by_date"][d]["baseline"]["brier"] -
                     result["by_date"][d]["with_depth"]["brier"] for d in dates])
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.6), layout="constrained")
    fig.suptitle("Does displayed size help predict the next BTC option midquote move?",
                 fontsize=14, weight="bold")
    months = [d[5:7] for d in dates]
    ax[0].bar(months, gain, color=np.where(gain >= 0,"#13766f","#b14d32"))
    ax[0].axhline(0,color="black",linewidth=.8)
    ax[0].set(title="Value added by imbalance", xlabel="2025 held-out month (first day)",
              ylabel="Brier score improvement over the baseline")
    buckets = result["imbalance_buckets"]
    x = np.arange(len(buckets))
    ax[1].plot(x,[100*b["up_rate"] for b in buckets], color="#20548a",marker="o")
    ax[1].axhline(50,color="#5b626f",linestyle="--",linewidth=.8)
    ax[1].set_xticks(x,["−1 to −.6","−.6 to −.2","−.2 to .2",".2 to .6",".6 to 1"])
    ax[1].tick_params(axis="x",labelsize=8)
    ax[1].set(title="Direction by best-level imbalance",xlabel="Bid minus ask size, divided by total size",
              ylabel="Upward share of observed moves (%)")
    for panel in ax:
        panel.spines[["top","right"]].set_visible(False)
        panel.grid(axis="y",alpha=.18)
    dest=ROOT / "docs/img/historical-replay.png"
    fig.savefig(dest,dpi=170)
    plt.close(fig)

    source = json.loads((ROOT / "results/replay/heatmap.json").read_text())
    depth = np.asarray([r if r is not None else [np.nan]*10 for r in source["sizes"]]).T
    fig, ax = plt.subplots(figsize=(9,3.8),layout="constrained")
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("#eeeeee")
    im = ax.imshow(depth,origin="lower",aspect="auto",interpolation="nearest",cmap=cmap,
                   extent=(1,20,-.5,9.5))
    ax.axhline(4.5, color="white", linewidth=1.2)
    ax.set_yticks(range(10),source["ranks"])
    ax.set(title=f"Displayed liquidity · {source['symbol']} · {source['date']} UTC",
           xlabel="Minutes since midnight UTC (gray = no fresh two-sided book)")
    fig.colorbar(im,ax=ax,label="Displayed size (BTC)")
    fig.savefig(ROOT / "docs/img/historical-liquidity.png",dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
