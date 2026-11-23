# Options Book Imbalance — interview notes

## What it is

A public options order-book recorder and a causal event study. It reconstructs snapshots and incremental updates, computes top-level size imbalance, and tests whether its sign predicts the next nonzero option-mid move at a fixed horizon. The bundled demo is synthetic; a longer live pilot produced an inconclusive, negative descriptive result.

## How it works and why

Deribit's public 100 ms book channel sends a full initial book followed by deltas. `change_id` and `prev_change_id` let me detect a missing update. After a gap the collector reconnects for a new snapshot and the evaluator refuses labels that cross the gap. I sum the top N bid and ask sizes, then divide their difference by the total. A positive value means more displayed bid size than ask size. The fixed prediction rule is sign(imbalance), with no trained threshold. I sample decision times at least a horizon apart, label from the first quote at or after the horizon, and split the resulting rows chronologically 70/30.

## Measured results and limits

Seed 7 of the deliberately predictive fixture: 501 updates, 500 labeled moves, 350 training and 150 holdout. The sign rule got 117/150 = 78%, with a Wilson 95% interval of about 70.7–83.9%; the training-majority baseline got 49.3%. The generator makes a move follow the previous imbalance sign 75% of the time. This is a correct-pipeline check, not evidence of live signal quality. No trading costs, fills, or exchange capture are represented.

On 24 November 2026 I recorded one live BTC option for 180 seconds: 339 messages, no sequence gaps or invalid books, 17 nonzero one-second labels. That is below the evaluator's minimum sample size; I report no live accuracy or profitability result.

I then recorded about 15 minutes of the same option across two WebSocket segments, reconnecting from a fresh snapshot after an empty close frame. The final file had 911 valid book messages. At one second, 482 decision times gave only 23 nonzero timely labels; 335 had an unchanged mid and 122 had no timely later quote. The chronological holdout had seven labels: the sign rule got two right and the majority baseline four. The announced 10-second sensitivity check also got two of seven versus four of seven. These samples are too small for a reliable conclusion, but there is no positive signal to claim from them.

## Two-minute STAR answer

**Situation:** I wanted to know whether displayed pressure in an options book has any short-horizon predictive value, and I wanted the result to survive a basic causal-data audit.

**Task:** Build a collector and evaluator that can replay public options-book updates, detect gaps, and avoid using future information in the signal.

**Action:** I recorded the design around Deribit's public option-book message format. The book starts from a snapshot and applies deltas only when sequence IDs line up. I compute normalized bid/ask size imbalance, take nonoverlapping decision times, use the first later quote after a fixed horizon for the label, and reserve the last 30% as holdout. I made a deterministic synthetic fixture with a planted relationship to check the whole path.

**Result:** On the fixture the rule got 78% direction accuracy versus a 49.3% majority baseline over 150 held-out decisions; the generator deliberately planted that signal. The longer live capture verified ingestion and gap checks but yielded only seven held-out labels, with the rule at 2/7 versus 4/7 for the baseline. I would present this as a study with an honest null/negative pilot, not a successful trading signal. The next evidence step is capture across several liquid instruments and regimes, with spread and underlying-move controls.

## Likely follow-ups

1. **Why use midquote rather than last trade?** Options trade infrequently; the mid gives more observations. It can be stale or non-executable, so I will compare trade or markout outcomes later.
2. **Does a positive imbalance imply a profitable buy?** No. The spread, fees, queue position and adverse selection could erase any predictive relation.
3. **What happens after packet loss?** A `prev_change_id` mismatch invalidates the local book; the collector reconnects and waits for a fresh snapshot. Analysis never labels across segments.
4. **How do you avoid look-ahead?** Feature extraction uses the book at decision time. Labels use only the first later quote at or after the predeclared horizon. The holdout is chronological.
5. **Why skip zero price moves?** The first question is conditional direction when the mid moves. That exclusion can bias interpretation, so a live report must also disclose the zero-move share and test a three-class formulation.
6. **Could the underlying drive the option price?** Yes. A live analysis should include synchronized underlying returns and IV/Greeks controls before attributing an effect to option-book pressure.
7. **Is this the whole option chain?** No. The collector records one chosen instrument per run. A chain study needs lifecycle handling, careful subscription limits and multiple-testing control.
8. **What does the 78% number prove?** Only that the pipeline recovers a signal intentionally planted in synthetic data. It says nothing about real-market predictability.

## Explain cold checklist

- Derive imbalance = (top-N bid size − top-N ask size) / (bid size + ask size).
- Explain snapshot, incremental update, and `prev_change_id` gap detection.
- Show how a label is chosen and why no segment crossing is allowed.
- Explain chronological split and majority baseline.
- State the synthetic fixture's planted 75% relation before quoting its 78% result.
- Name the missing live controls: underlying, spread, IV, liquidity, fees and multiple horizons.
