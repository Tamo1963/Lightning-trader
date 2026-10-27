# Defined-risk intraday option selling: results (2026-10-27)

Protocol: `2026-10-27-selling-preregistration.md` (committed before implementation). Raw tables:
`2026-10-27-selling-train.csv`, `2026-10-27-selling-validation-top3.csv`. Test split sealed, not run.

## Outcome: not confirmed
- **Train:** all 16 variants strongly negative (-0.32R to -0.45R; win rates 1-6%). `iv_high` days were worse than unfiltered.
- **Validation (top 3):** fly|1200|stop_tp|none -0.49R (CI -0.57..-0.42); condor|1200|time|none -0.52R; fly|1200|time|none -0.51R.

## Was it a bug? Checked
The 1-6% win rate looked implausible, so it was traced:
1. Raw data: the near-expiry ATM straddle does decay intraday (12:00 -> 15:15: mean -9.9 pts, median -8.8 pts, n=375).
2. A traced trade (2021-11-09): mid-to-mid the fly gained only about 1.3 pts because the 150-pt wings decayed almost as
   much as the short strikes; 4-leg slippage (about 5.5 pts round trip) turned it into a loss.
3. **Same rules with zero slippage (train, 12:00 entry, square-off):** fly -2.99 pts/unit mean (median -0.18, 49% wins),
   condor -2.78 (median +0.09, 52% wins). So even at perfect mid fills there is no edge: time decay is roughly cancelled
   by losses on large-move days, and slippage on four legs makes it clearly negative.

## Reading
Intraday, at 2+ days to expiry, the hedged short premium earns too little decay (the wings decay too) to cover
large-move days, before any execution cost. The pre-registered slippage (1% per leg, min 0.5 pt) may be pessimistic
for liquid ATM Nifty strikes, but the zero-slippage check shows the conclusion does not depend on it.
13-22% of leg prices were modelled (strike outside the fetched band), mostly far wings after the index moved.

Not tested (outside this pre-registration): holding to expiry or overnight, 0-1 DTE (expiry-day block is a standing
choice), wider wings beyond the fetched ATM+/-3 band.
