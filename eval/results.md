# Memory OFF vs ON: simulation on synthetic data

40 simulated sellers, 458 fought held-out disputes. Outcomes are drawn from a hidden ground-truth win model,
so this shows the mechanism, not real-world performance. Reproduce: `python eval/run_eval.py --sellers 40`.

| | Memory OFF | Memory ON | Oracle |
|---|---|---|---|
| Brier score of win probability (lower = better) | 0.254 | 0.233 | - |
| Mean profit per fought dispute (USD) | 31.32 | 31.66 | 32.88 |
| "Accept" advice that was right | 75/129 | 56/84 | - |

