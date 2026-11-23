# Options order-book imbalance research

## A two-minute explanation

The first live trial answered a narrower question than I expected. A BTC option could receive hundreds of size updates while its midquote barely moved. There were only seven held-out price moves and the rule got two right. That motivated a historical replay where I could count both the book updates and the decisions that actually had an observable price change.

The replay uses first-of-month BTC option books from Deribit. At each decision it records bid and ask sizes, the spread, and the direction of the most recent mid change. It waits up to ten seconds for the same contract's next distinct midquote. No second trial for that contract can use the same waiting interval. The models fit on 2024 windows and are evaluated on subsequent 2025 windows.

The simple best-level rule got 65.18% of 158,484 held-out moves right. The five-level sign rule got 56.06%. With a baseline that already includes other options' recent price moves, adding imbalance raised accuracy from 61.64% to 65.20%. The trading check changed the interpretation. Crossing the spread at entry and exit gave the best-level rule an average outcome of approximately minus one entry spread before fees. I would use the result to motivate studying quote placement and adverse selection. Passive execution still needs an order-flow and fill model.

## Questions to be ready for

1. **What exactly did you predict?** The direction of the next distinct midpoint in a single option book within ten seconds. Of 429,880 held-out decisions, 158,484 had a valid label. The score does not answer whether a move will occur.
2. **Why did the best level help?** Its quantities sit immediately at the prices that determine the midpoint. Empirically, the up rate ranged from 27.6% in the most ask-heavy best-level bucket to 77.8% in the most bid-heavy bucket. The study measures the association and does not identify its cause.
3. **Why compare against other contracts?** Many options respond to the same BTC move. The supplementary control gives each other recently moving contract one vote from the previous full second, with sign adjusted for puts. It excludes the target. Imbalance still improved Brier score from 0.2286 to 0.2095.
4. **How did you guard against leakage?** Split by calendar year, process each symbol separately in receipt order, coalesce equal timestamps, break labels at bad books, and fit both scaler and coefficients only on 2024. The ledger audit checks every outcome against the saved entry and exit prices and checks intervals for overlap.
5. **Why does positive accuracy coexist with negative economics?** A correct next-mid move can be much smaller than a round-trip spread. Signed mid movement averaged +0.066 starting spreads for the best-level sign rule. Crossing both touches reduced that to −0.994 under immediate infinitesimal fills and zero fees.
6. **How precise are the results?** Scores use 158,484 moves, but these span only 11 held-out dates and many contracts share an underlying. The primary Brier improvement was positive on each date. Resampling whole dates gave 0.0166–0.0245. The interval cannot address times of day the project never observed.
7. **What happened to the original one-second rule?** On archive replay the five-level rule got 58.27% of 43,332 nonzero, timely, non-tied moves correct. The original live pilot, the fixed-horizon archive result, and the next-distinct-move result have different denominators.
8. **What did you contribute?** Be precise about the parts you personally ran, inspected, changed or can derive. The checksum manifest, tests, scripts and ledger make the study's claims reviewable. Avoid claiming work you cannot explain.

## Explain without notes

- Compute size imbalance as (bid size − ask size) / (bid size + ask size).
- Draw a timeline with two equal timestamps, a prediction time and its later midquote change.
- Trace one long and one short through bid/ask entry and exit.
- Distinguish the live WebSocket pilot from the archived 2025 holdout.
- Explain why 11 session blocks matter even with more than 150,000 labels.
