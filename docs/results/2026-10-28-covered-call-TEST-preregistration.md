# Sealed test of the 5% covered call: pre-registration (committed BEFORE the test data is downloaded)

This is the one and only use of the test period for this idea.

- **Rule under test:** C5 from `2026-10-28-hedged-futures-preregistration.md`: long next-month futures rolled on the last
  trading day before each monthly expiry, plus a short call at the strike nearest F x 1.05 on the same expiry, bought back
  at the close of the day before expiry. Same costs, fills (daily closes), stale-close guard and corporate-action filter.
- **Universe (fixed from train):** the 13 underlyings that passed the liquidity screen: AXISBANK, BHARTIARTL, HDFCBANK,
  ICICIBANK, INFY, ITC, LT, M&M, RELIANCE, SBIN, SUNPHARMA, TATASTEEL, TCS.
- **Test cycles:** every complete cycle whose expiry falls between 2025-10-01 and 2026-10-31 (about 13 per stock;
  no overlap with validation, whose cycles all expired by 2025-09-30).
- **Pass (all required):**
  1. Sharpe(C5) > Sharpe(B0) in at least 9 of the 13 stocks;
  2. median annualised return change (C5 - B0) across the 13 >= -2 percentage points;
  3. median max-drawdown ratio (C5 / B0) <= 1.0.
- Reported regardless: per-stock return, Sharpe, drawdown for both; pooled monthly returns across stocks.
- No parameter, universe or rule may change after this file is committed.
