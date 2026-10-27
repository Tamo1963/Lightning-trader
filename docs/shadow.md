# Shadow testing runbook

Shadow mode runs the full decision pipeline on live market data and **paper-trades at real bid/ask quotes. It places
no orders**: the Dhan client in this repository has no order methods, and a test fails if one is added.

## What it records (SQLite: `data/shadow/live.sqlite`)
| Table | Content |
|---|---|
| `bars` | completed 15-min Nifty bars with the option-volume proxy used for VWAP/VWMA |
| `candidates` | every candidate per strategy, with features, code version, config hash |
| `gates` | G1..G5 result and reason per candidate (G3 is a recorded pass-through: no validated stats model) |
| `jev_calls` | raw Jev request/response, aggregated probabilities, decision, latency, errors |
| `paper_trades` | entry at the ask, exit at the bid; P&L at fills and at mid (difference = real spread cost) |
| `quotes` | ATM+/-3 calls and puts each bar, plus held contracts: bid, ask, IV, OI, cumulative volume |
| `heartbeat` | one row per step, plus POLL_ERROR / STEP_ERROR with details |

Every candidate that passes the trade-level checks is paper-traded **whatever Jev says**, so "A" (all) and "A+J"
(Jev-approved) are compared on identical candidates. Account-level limits are recorded as `would_block`, not enforced.

## Setup (on a machine that stays on during market hours; the cloud session container is not suitable)
1. `pip install -r requirements.txt` (plus `typesafe-sdk` for Jev).
2. Environment variables (never commit them):
   - `DHAN_ACCESS_TOKEN` (refresh daily), `DHAN_CLIENT_ID` (required by the option-chain endpoint),
   - `JEV_API_KEY` (optional; without it every Jev decision is logged as `UNAVAILABLE`).
3. Keep `config/shadow.yaml` and the risk/cost configs under version control; their hash is stored on every candidate.

## Daily run
```
python scripts/run_shadow.py --live          # start before 09:15 IST; exits by itself after 15:35
streamlit run app/dashboard.py               # read-only dashboard
touch data/shadow/STOP                       # kill switch (remove the file before the next run)
```
Example cron (Mon-Fri, server in IST): `5 9 * * 1-5 cd /path/lightning-trader && . ./.env && python scripts/run_shadow.py --live >> data/shadow/run.log 2>&1`

## Behaviour
- Steps 15 s after each 15-min boundary; polls quotes every 20 s while paper positions are open (stop/target).
- Fails closed: stale bars (> 120 s late), special sessions (not opening at 09:15), expiry day, missing quotes, spread
  above 3% of premium, Jev errors/timeouts (-> REJECT). Exceptions are logged and the loop continues.
- Restart-safe: open paper trades and stored bars are reloaded from the database.
- First live day: VWMA(20) needs 20 bars of the live volume proxy, so early-session candidates on day 1 are missing.

## Offline check
`python scripts/run_shadow.py --replay --from 2024-06-03 --to 2024-06-28` replays stored data through the same engine
(synthetic 0.5% half-spread). On that month it reproduces the backtest's 23 baseline candidates exactly.

## What to look at after a few weeks
1. **Spreads tab:** the real round-trip cost vs the 2% assumed in every backtest.
2. **Jev tab:** error rate, latency, approval rate by direction (buy-bias check).
3. **Paper trades:** A vs A+J on identical candidates; note that both strategies already failed backtests, so a
   positive forward result needs the same pre-registered evaluation before anything else.
