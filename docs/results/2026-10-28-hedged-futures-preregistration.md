# Futures with option hedges (insured buy-and-hold, covered calls): pre-registration

Committed BEFORE any data for this study was downloaded. These are portfolio overlays on a permanent long futures
position, not signal strategies, so each is judged against plain futures buy-and-hold on the same underlying.

## Underlyings
BANKNIFTY, NIFTY (reference), and the 20 stocks in `config/stocks.yaml` (survivorship bias: today's large caps; it
mostly affects the buy-and-hold baseline, less the overlay-vs-baseline comparison).
**"Can be used consistently" (liquidity screen, train period only):** an underlying qualifies if on >= 90% of roll
days both the 3% and 5% out-of-the-money options used below traded (volume > 0) in the next-month expiry. Underlyings
that fail are reported but excluded from the verdict.

## Strategies (5 per underlying), monthly cycles, all fills at NSE bhavcopy daily closes
- **B0 buy-and-hold:** long 1 unit of near-month futures; on the last trading day before each monthly expiry, sell the
  expiring contract and buy the next month at the close.
- **P3 / P5 insured:** B0 + buy the next-month put with strike nearest to F x (1 - 3%) / (1 - 5%) at the roll; sell it at
  the close of the day before its expiry.
- **C3 / C5 covered call:** B0 + sell the next-month call nearest to F x (1 + 3%) / (1 + 5%) at the roll; buy it back at
  the close of the day before its expiry.
- Option exit marks are floored at intrinsic value (stale-close guard). Strikes from the listed strikes that day.
- Costs: futures slippage 0.01% of price per side; options max(1% of price, 0.5 tick-units of 0.05) per side, i.e.
  max(1%, 0.05); charges per `config/costs.yaml` (options) and futures STT 0.02% on sell, exchange 0.00173% [VERIFY].
- Returns per cycle on futures notional at the roll (fully collateralised; interest on collateral ignored).
- Corporate actions: a stock-cycle is excluded if any day's futures close moves more than 30% (split/bonus adjustment).

## Metrics
Annualised return, annualised volatility, Sharpe (rf = 0), max drawdown, worst cycle; per calendar year as well.

## Verdict rules (fixed now)
For each qualifying underlying and overlay X in {P3, P5, C3, C5}:
- **Covered call (C3, C5) "worth it"** if Sharpe(X) > Sharpe(B0) in train AND validation AND in >= 70% of train years.
- **Insurance (P3, P5) "worth it"** if max drawdown(X) <= 0.7 x max drawdown(B0) in train AND validation, AND the
  annualised return given up (B0 - X) is <= 3 percentage points in both.
Summary: per overlay, the number of qualifying underlyings where it is "worth it". Train 2016-01..2024-06, validation
2024-07..2025-09; test not downloaded.
