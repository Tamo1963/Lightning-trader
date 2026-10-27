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
python -m pytest -q                                    # 30 tests (look-ahead, pricing, calendars, Dhan client)
export DHAN_ACCESS_TOKEN=...                           # environment only; never commit or print
python scripts/fetch_history.py --start 2021-11-01 --end 2026-10-27   # resumable; writes data/NIFTY/
python scripts/run_baseline.py --data-dir data/NIFTY   # real expired-option premiums
python scripts/run_baseline.py --synthetic             # plumbing check on FAKE data
```

Data (all from DhanHQ, Nifty 50 = security ID 13):
- `spot_daily.csv` (monthly/weekly RSI), `spot_15m.csv` (signals; 5 years available)
- `options/`: rolling expired options, near and next weekly expiry, ATM-3..ATM+3, calls and puts, 15-min OHLC + IV, OI, volume, spot
- Expired futures intraday is not available, so VWAP/VWMA are weighted by option volume (same proxy must be used live).

Modules: `indicators`, `features`, `signals` (G1/G2), `calendar` (expiry and lot-size history, holiday shifts),
`pricing` (RealPricer from Dhan data, ModelPricer fallback), `costs`, `backtest` (triple barrier, risk limits),
`metrics` (day-clustered bootstrap), `data/` (Dhan client, store, synthetic data for tests only).

Still [VERIFY] on first fetch: which Dhan `expiryCode` is the near weekly contract (config `data.rolling_slots`),
pre-2025 expiry weekday and lot sizes, and the charges in `config/costs.yaml`.
