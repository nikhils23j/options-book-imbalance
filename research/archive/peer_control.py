"""A stricter baseline using only earlier, other-contract observations."""
import json
import numpy as np
import pandas as pd

from fetch import ROOT, STORE, DATES
from replay import US, COLS, FEATURES, prepare, day_events
from study import OUT, fit, score_predictions, SEED


def pressure(books, events):
    prior = books.groupby("symbol", sort=False).shift()
    mid2 = books.bid + books.ask
    change = mid2 - prior.bid - prior.ask
    active = (books.valid & prior.valid.eq(True) &
              ((books.local_timestamp-prior.local_timestamp) <= 2*US) & change.ne(0))
    taps = pd.DataFrame({"symbol":books.symbol, "sec":books.local_timestamp//US,
                         "change":change})[active]
    net = taps.groupby(["sec","symbol"]).change.sum()
    votes = np.sign(net[net.ne(0)]) * np.where(net[net.ne(0)].index.get_level_values("symbol").str.endswith("-P"),-1,1)
    total = votes.groupby(level="sec").agg(["sum","count"])
    last_sec = events.decision_us//US - 1
    prior_sum = total["sum"].reindex(last_sec, fill_value=0).to_numpy()
    prior_count = total["count"].reindex(last_sec,fill_value=0).to_numpy()
    own = votes.reindex(pd.MultiIndex.from_arrays([last_sec,events.symbol]),fill_value=0).to_numpy()
    denom = prior_count - (own != 0)
    peer_mean = np.divide(prior_sum-own,denom,out=np.zeros(len(events)),where=denom>0)
    return peer_mean * np.where(events.is_put,-1,1)


def main():
    rows = []
    for day in DATES:
        path = STORE/(day+".csv.gz")
        events, _, _ = day_events(path,day)
        books = prepare(pd.read_csv(path,usecols=COLS))
        events["peer_pressure"] = pressure(books,events)
        rows.append(events)
    data = pd.concat(rows,ignore_index=True)
    train, test = data[data.date < "2025"], data[data.date >= "2025"].copy()
    metrics = {}
    for name, columns in [("peer_baseline",FEATURES[:3]+["peer_pressure"]),
                          ("peer_plus_depth",FEATURES+["peer_pressure"])]:
        model = fit(train,columns)
        test[name] = model.predict_proba(test[columns])[:,1]
        metrics[name] = score_predictions(test,name,True)
    test["gain"] = (test.up-test.peer_baseline)**2 - (test.up-test.peer_plus_depth)**2
    groups = test.groupby("date").gain.agg(["sum","count","mean"])
    idx = np.random.default_rng(SEED).integers(0,len(groups),size=(4000,len(groups)))
    boot = groups["sum"].to_numpy()[idx].sum(axis=1)/groups["count"].to_numpy()[idx].sum(axis=1)
    metrics.update(gain=float(test.gain.mean()),bootstrap95=np.quantile(boot,[.025,.975]).tolist(),
                   by_date=groups["mean"].to_dict(), fraction_nonzero_peer=float(test.peer_pressure.ne(0).mean()))
    (OUT/"peer-control.json").write_text(json.dumps(metrics,indent=2)+"\n")


if __name__ == "__main__":
    main()
