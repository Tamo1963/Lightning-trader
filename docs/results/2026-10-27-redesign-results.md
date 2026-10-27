# Redesign grid: results (2026-10-27)

Protocol: `2026-10-27-redesign-preregistration.md` (committed before running). Raw tables:
`2026-10-27-grid-train.csv`, `2026-10-27-grid-validation-top3.csv`. Test split sealed, not run.

## Outcome: no variant confirmed
- **Train:** all 24 variants have negative net expectancy (best: pullback|60m|full, -0.070R, CI -0.159..+0.023).
- **Validation (top 3 by train):** pullback|60m|full -0.160R (CI -0.251..-0.065); edge|30m|none -0.086R;
  pullback|30m|no_monthly -0.107R. Candidate **not confirmed**.

## Why: the signals have no forward direction
Index move in the trade direction from next-bar entry to the horizon, in ATR units (train, all candidates):
every one of the 24 combinations is negative (-0.02 to -0.20 ATR; hit rates 44-53%). Trend-following 15-min rules
on Nifty did not predict continuation in 2021-2024; if anything there is mild reversion. Since options cannot add
direction that the underlying does not have, no barrier, horizon or strike choice can rescue this rule family.

Rough break-even for an ATM option buyer (delta ~0.5): slippage both sides + charges + time decay need about
0.3-0.4 ATR of favourable index move per trade (estimate, not measured). The largest effect seen (about 0.2 ATR,
in the wrong direction) is below that, so inverting the signal is also unlikely to pay.

## Recommendation
Stop tuning this rule family (more variants on the same data mostly add false-discovery risk). Choose a new
hypothesis family, pre-register it, and test it the same way. Jev work stays on hold until some baseline passes gate 1.
