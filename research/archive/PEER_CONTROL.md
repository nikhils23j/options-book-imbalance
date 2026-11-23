# Additional control for common BTC repricing

This secondary comparison was specified before inspecting held-out model scores. It supplements the frozen primary baseline.

For each decision, look back to the previous complete UTC second. Each other BTC option with a valid recent mid change votes once according to its net price movement in that second. Reverse put votes before averaging so that an upward call or a downward put votes for upward underlying pressure. Exclude the target instrument. Reverse the resulting signal for put targets and use zero when no other contract voted. Use the fraction as an extra feature for both logistic models with the original split and specifications. It is a proxy for common repricing across options and can reflect volatility and skew as well as the underlying.
