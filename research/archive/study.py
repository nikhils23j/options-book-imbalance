"""Run the frozen calendar split and publish aggregate, auditable results."""
from __future__ import annotations
import hashlib
import json
import os
import platform
import sys
import time
from collections import Counter

import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from fetch import DATES, STORE, ROOT, checksum
from replay import day_events, FEATURES

OUT = ROOT / "results" / "replay"
SEED = 7301
MODELS = ["majority", "sign_l1", "sign_l5", "baseline", "with_depth", "shuffled_depth"]


def fit(train, features):
    model = make_pipeline(StandardScaler(), LogisticRegression(C=1, max_iter=500))
    return model.fit(train[features], train.up)


def score_predictions(frame, prefix, probabilistic):
    p = frame[prefix].to_numpy()
    pred = p >= .5
    up = frame.up.to_numpy(dtype=bool)
    correct = pred == up
    ret = dict(n=len(frame), correct=int(correct.sum()), accuracy=float(correct.mean()),
               up=int(up.sum()), tp=int((pred & up).sum()), fp=int((pred & ~up).sum()),
               tn=int((~pred & ~up).sum()), fn=int((~pred & up).sum()))
    if probabilistic:
        bounded = np.clip(p, 1e-12, 1-1e-12)
        ret.update(brier=float(np.mean((p-up.astype(float))**2)),
                   log_loss=float(np.mean(np.where(up, -np.log(bounded), -np.log1p(-bounded)))))
    return ret


def report(frame):
    return {m:score_predictions(frame, m, m in ("baseline", "with_depth", "shuffled_depth","majority"))
            for m in MODELS}


def economics(frame, model):
    direction = np.where(frame[model] >= .5, 1., -1.)
    spread = frame.entry_ask - frame.entry_bid
    mid_move = (frame.exit_ask + frame.exit_bid - frame.entry_ask - frame.entry_bid)/2
    signed = direction * mid_move / spread
    crossed = signed - .5 - .5 * (frame.exit_ask - frame.exit_bid) / spread
    return dict(mean_mid_spreads=float(signed.mean()), mean_crossed_spreads=float(crossed.mean()),
                median_crossed_spreads=float(crossed.median()), positive_crossed_share=float((crossed>0).mean()))


def summarize(train, test):
    test = test.copy().reset_index(drop=True)
    prob_up = float(train.up.mean())
    test["majority"] = prob_up
    for level in ("l1", "l5"):
        test["sign_"+level] = np.where(test[level] == 0, float(prob_up>=.5), (test[level]>0).astype(float))
    models = {}
    for name, columns in (("baseline", FEATURES[:3]), ("with_depth", FEATURES)):
        estimator = fit(train, columns)
        models[name] = estimator
        test[name] = estimator.predict_proba(test[columns])[:, 1]
    rng = np.random.default_rng(SEED)
    permuted = test[FEATURES].copy()
    for idx in test.groupby(["date", "is_put"]).indices.values():
        permuted.loc[idx, ["l1", "l5"]] = test.loc[rng.permutation(idx), ["l1", "l5"]].to_numpy()
    test["shuffled_depth"] = models["with_depth"].predict_proba(permuted)[:, 1]
    by_date = {d:report(g) for d,g in test.groupby("date")}
    daily_n = np.array([scores["baseline"]["n"] for scores in by_date.values()])
    improvements = np.array([scores["baseline"]["brier"]-scores["with_depth"]["brier"]
                             for scores in by_date.values()])
    sampled = np.random.default_rng(SEED).integers(0, len(by_date), (4000, len(by_date)))
    boot = (improvements[sampled] * daily_n[sampled]).sum(axis=1) / daily_n[sampled].sum(axis=1)
    bins = pd.cut(test.l1, [-1.001,-.6,-.2,.2,.6,1.001])
    return test, dict(scores=report(test), by_date=by_date,
                      by_side={("put" if side else "call"):report(g) for side,g in test.groupby("is_put")},
                      economic_diagnostic={m:economics(test,m) for m in ("sign_l1","sign_l5","baseline","with_depth")},
                      imbalance_buckets=[dict(bin=str(k),n=len(g),up_rate=float(g.up.mean()))
                                         for k,g in test.groupby(bins,observed=True)],
                      paired_brier_gain=float(np.average(improvements, weights=daily_n)),
                      equal_date_brier_gain=float(improvements.mean()),
                      brier_gain_sessions=int((improvements>0).sum()),
                      bootstrap95=np.quantile(boot,[.025,.975]).tolist(),
                      train_up_probability=prob_up,
                      standardized_coefficients={m:dict(zip(FEATURES, est[-1].coef_[0].tolist()))
                                                 for m,est in models.items()})


def main():
    started = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((STORE / "manifest.json").read_text())
    if set(manifest) != set(DATES):
        raise RuntimeError("Run fetch.py to complete the archive manifest first")
    frames, counts, fixed = [], {}, {}
    for day in DATES:
        path = STORE / (day+".csv.gz")
        if checksum(path) != manifest[day]["sha256_csv"]:
            raise ValueError(f"checksum mismatch on {day}")
        frame, counts[day], fixed[day] = day_events(path, day)
        if len(frame) == 0 or counts[day]["raw_snapshots"] != manifest[day]["rows"]:
            raise ValueError(f"invalid coverage on {day}")
        frames.append(frame)
        print(day, len(frame), "labels", flush=True)
    all_rows = pd.concat(frames, ignore_index=True)
    train, test = all_rows[all_rows.date < "2025"], all_rows[all_rows.date >= "2025"]
    test, result = summarize(train,test)
    early = sum((Counter(fixed[d]) for d in DATES if d < "2025"), Counter())
    late = sum((Counter(fixed[d]) for d in DATES if d >= "2025"), Counter())
    baseline_correct = late["up"] if early["up"] * 2 >= early["scored"] else late["scored"]-late["up"]
    result["fixed_horizon"] = dict(train=dict(early), test=dict(late), daily=fixed,
                                   accuracy=late["correct"]/late["scored"],
                                   baseline_accuracy=baseline_correct/late["scored"])
    test.to_csv(OUT / "decisions-holdout.csv.gz", index=False, float_format="%.12g")
    result.update(protocol_sha256=hashlib.sha256((ROOT/"research/archive/PROTOCOL.md").read_bytes()).hexdigest(),
                  source_manifest_sha256=hashlib.sha256((STORE/"manifest.json").read_bytes()).hexdigest(),
                  daily_counts=counts, train_labels=len(train), test_labels=len(test),
                  train_contracts=train.symbol.nunique(), test_contracts=test.symbol.nunique(),
                  seed=SEED, bootstrap_draws=4000, repetitions=1, command="python research/archive/study.py",
                  environment=dict(python=sys.version.split()[0],os=platform.system(),numpy=np.__version__,
                                   pandas=pd.__version__,sklearn=sklearn.__version__,load_average=list(os.getloadavg())),
                  elapsed_seconds=round(time.monotonic()-started,2))
    (OUT/"summary.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({k:result[k] for k in ("test_labels","paired_brier_gain","bootstrap95","scores")},indent=2))


if __name__ == "__main__":
    main()
