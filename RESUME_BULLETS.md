# Options Order-Book Imbalance Study
Portfolio research · Python, NumPy, pandas, scikit-learn

- Replayed 4.37M Deribit BTC option-book snapshots across 23 sessions. On 158,484 held-out midquote moves within ten seconds, best-level size imbalance predicted direction with 65.2% accuracy versus 56.1% using five-level imbalance.
- Controlled for spread, previous price direction, option type and recent moves in other BTC options. Adding imbalance cut held-out Brier score from 0.229 to 0.210 and raised accuracy from 61.6% to 65.2%.
- Measured the execution cost of the best-level signal. A +0.066-spread average signed midquote move became −0.994 spreads after crossing both displayed quotes, before fees.

Use the first and third bullets if only two lines of evidence fit. Results describe an archived, conditional-direction study. The execution comparison assumes immediate small fills.
