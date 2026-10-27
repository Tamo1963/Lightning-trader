# Stock options study: pre-registration (committed BEFORE data download, implementation and any run)

Universe: 20 large-cap F&O stocks in `config/stocks.yaml` (survivorship bias: today's large caps). Buyer of ATM
monthly stock options, one lot per signal, results in R = net P&L / premium paid (no premium stop: max loss = premium).

## Two stages
- **Stage 1 (now; option-price data unavailable from Dhan):** stock prices from Dhan; option P&L **modelled** with
  Black-76 (r = 0), IV = 1.1 x 20-day realized volatility at entry (constant through the hold), slippage 1% of premium
  per side (min 0.05), charges from `config/costs.yaml`. Plus the stock's own move in the trade direction (t-stat).
- **Stage 2 (when Dhan's expired-options endpoint works):** survivors re-tested with real option prices (ATM+/-2,
  near and next month). **Nothing counts as confirmed on modelled prices.**

## Rollover / expiry
Monthly stock options expire on the last expiry weekday of the month (Thursday until 2025-08, Tuesday from 2025-09;
holidays move it to the previous trading day). At entry, pick the first monthly expiry at least (holding period + 7)
calendar days away, so no position is held into expiry week. Multi-period strategies roll by exiting and re-entering at
each rebalance into the then-appropriate expiry (each leg counts as a trade).

## Variants (7)
| Id | Family | Signal | Entry / exit |
|---|---|---|---|
| S1a, S1b | Intraday baseline rules on each stock (15-min): monthly RSI>50 (<50), weekly RSI change >0 (<0), close > (<) VWAP, VWMA(20), SuperTrend(10,3); first bar all true; decisions 09:30-14:30 | next-bar open; exit after 30 min (S1a) or at 15:15 (S1b) |
| S2a, S2b, S2c | Daily version of the same rules: monthly RSI and weekly RSI change as above, daily close > (<) daily VWMA(20) and daily SuperTrend(10,3); first day all true | next-day open; hold 5 / 10 / 20 trading days, exit at close |
| S3a, S3b | Cross-sectional momentum: on the first trading day of each month rank the 20 stocks by return from t-252 to t-21 (S3a) or t-126 to t-21 (S3b); calls on the top 3, puts on the bottom 3 | entry at that day's open, exit at the close before the next month's first trading day; then re-rank and roll |

## Selection rule (fixed now)
1. Train: 2016-01-01..2024-06-30 for S2/S3 (daily data), 2021-11-01..2024-06-30 for S1. Eligible: >= 100 trades.
2. Rank eligible variants by train mean modelled R. Candidate = top-ranked variant whose train stock-move t-stat (in trade
   direction, clustered by entry date) is > 2. If none has t > 2, stage 1 stops: no candidate.
3. Validation (2024-07-01..2025-09-30): top 3 by train R. Stage-1 pass for the candidate requires validation mean R > 0
   and 90% date-clustered bootstrap CI lower bound > 0.
4. Stage-1 passers go to stage 2. Test split sealed.
