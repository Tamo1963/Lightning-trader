# Monthly hedged selling with a 5% profit target: results (2026-10-28)

Protocol: `2026-10-28-monthly-selling-preregistration.md` (frozen before download). Data: NSE bhavcopy, 2,406 trading
days 2016-01..2025-09, Nifty monthly options. Test period not downloaded. Tables: `2026-10-28-monthly-selling-*.csv`.

## Outcome: not confirmed
- **Train (2016-01..2024-06, ~100 cycles):** all 12 variants negative. Best: condor_w|mid|none -0.017R (CI -0.073..+0.036).
- **Validation (2024-07..2025-09, 15 cycles):** condor_w|mid|none -0.108R (CI -0.308..+0.056); condor_n|mid|none -0.079R;
  condor_w|mid|stop10 -0.068R. Candidate **not confirmed**.

## Why: the payoff is lopsided
- The 5% target is hit often (73-83% of cycles for the mid-month variants), but a win is capped at +0.05R while a missed
  cycle loses about -0.65R on average (up to about -1R; a gap can jump past the -10% stop to the full max loss).
- Break-even needs roughly 0.65 / (0.65 + 0.05), i.e. about 93% target hits; the best variant reached 82%.
- With 20% of equity employed per cycle, the worse variants lost almost all capital over 2016-2024 (net about -INR 9.9 lakh
  of 10 lakh), so risk of ruin is real even with defined-risk spreads.
- Entering mid-month (about 2 weeks left) beat entering right after expiry in every pairing; the -10% stop cut the size
  of losses but triggered too often to help.

## Data check (found after the run, reported openly)
Bhavcopy "close" for options is the last trade, which can be stale for deep in-the-money strikes: 12.5% of 300-pt call
spreads in the files show a value above their width (impossible), mostly on large-move days when sellers lose.
**Sensitivity run (not pre-registered):** capping each vertical's mark to [0, width] changes little (best train variant
-0.028R; same validation result), so the failure is not a data artifact.

## Reading
Selling monthly premium with a small fixed profit target trades many small wins for occasional large losses, and on
2016-2025 Nifty data the losses win. The independent "insurance premium" evidence does not survive these rules,
realistic slippage on four legs, and charges.
