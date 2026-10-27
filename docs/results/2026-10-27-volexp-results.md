# Volatility-expansion family: results (2026-10-27)

Protocol: `2026-10-27-volexp-preregistration.md` (committed before implementation). Raw tables:
`2026-10-27-volexp-train.csv`, `2026-10-27-volexp-validation-top3.csv`. Test split sealed, not run.

## Outcome: not confirmed
- **Train:** 10 of 12 variants negative. The only two positive variants (OR60|compression|EOD +0.054R, CI -0.240..+0.358;
  OR60|compression|60m +0.007R) had 58 trades each, below the pre-registered eligibility floor of 60, so they were not
  selected. Their intervals are wide and span zero by a large margin.
- **Selected candidate OR60|none|EOD:** train -0.021R (CI -0.148..+0.113), validation **-0.259R (CI -0.418..-0.087)**.
  Not confirmed. Ranks 2-3 (OR60|low_iv|60m and EOD) are also clearly negative on validation (about -0.29R).

## What the index did
- Train (2021-11..2024-06): 60-min opening-range breakouts held to the close moved +0.24 ATR in the breakout
  direction (+0.45 ATR after compression days). That is close to, but below, the ~+0.3 ATR an ATM option buyer needs.
- Validation (2024-07..2025-09): the same breakouts **reversed**: -0.11 to -0.21 ATR. Continuation in 2021-2024 did not persist.
- 30-min opening ranges were worse than 60-min in every pairing.

## Reading
The breakout effect is regime-dependent and too small for option buyers after slippage, charges and time decay.
The compression effect is the only hint of something, on 58 trades. It would need its own pre-registered
confirmation on validation; it has not been looked at there.
