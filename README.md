# Lightning Trader

Quantitative options-buying engine for Nifty 50 and Bank Nifty (DhanHQ), with Jev AI as a
single, bounded approve/reject gate. Code generates candidates, estimates edge, sizes risk and
executes. Jev can only veto. It can never override the risk engine.

Status: **foundation spec (v0.1, draft)**. Nothing here trades yet.

- `docs/execution-plan.md`: the end-to-end plan (start here)
- `docs/foundation-spec.md`: scope, gates, risk rules, backtest protocol, acceptance criteria
- `schemas/jev_questions.json`: Jev typed question set (provisional)
- `schemas/audit.sql`: decision and trade audit tables
- `config/risk.defaults.yaml`: hard-coded risk limits (placeholders to tune before freeze)

## Code (Phase 2: data layer and baseline backtest)

```
pip install -r requirements.txt
python -m pytest -q                         # 22 tests, including look-ahead and mutation-checked leak tests
python scripts/run_baseline.py --synthetic  # plumbing check on FAKE data
python scripts/fetch_dhan.py ...            # real data (DHAN_ACCESS_TOKEN env var), then run_baseline.py --fut ... --daily ...
```

- `lightning/indicators.py`, `features.py`, `signals.py`: causal indicators, completed-period higher-timeframe RSI, baseline G1/G2
- `lightning/options.py`, `costs.py`, `backtest.py`, `metrics.py`: modelled premiums, charges, triple-barrier simulator, risk limits, day-clustered bootstrap
- `lightning/data/`: Dhan client, CSV store with validation, contract stitching, synthetic generator (tests only)

Known limits: premiums are modelled (constant IV, no spread) until real option history is wired in; weekly-expiry
calendar ignores holidays; futures contracts must be fetched and stitched per expiry.
