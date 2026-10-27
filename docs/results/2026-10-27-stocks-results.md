# Stock options study, stage 1: results (2026-10-27)

Protocol: `2026-10-27-stocks-preregistration.md` (committed before download and implementation). 20 large-cap F&O stocks,
real Dhan stock prices, **modelled** ATM monthly option P&L (IV = 1.1 x 20-day realized vol). Raw tables:
`2026-10-27-stocks-train.csv`, `2026-10-27-stocks-validation.csv`. Test split sealed.

## Train (S2/S3: 2016-01..2024-06; S1: 2021-11..2024-06)
| Variant | Trades | Mean R | 90% CI | Stock move in trade direction (t) |
|---|---|---|---|---|
| S2b daily rules, hold 10 days | 1,368 | **+0.097** | +0.040..+0.157 | +0.51% (2.68) |
| S2c daily rules, hold 20 days | 1,006 | +0.093 | +0.019..+0.168 | +0.52% (1.49) |
| S3a momentum 12-1, monthly roll | 606 | +0.059 | -0.016..+0.141 | +0.16% (0.48) |
| S3b momentum 6-1, monthly roll | 612 | +0.042 | -0.041..+0.128 | +0.04% (0.12) |
| S2a daily rules, hold 5 days | 1,541 | +0.042 | +0.002..+0.085 | +0.17% (1.10) |
| S1b intraday rules, to close | 4,306 | -0.011 | -0.021..-0.001 | +0.01% (-1.85) |
| S1a intraday rules, 30 min | 8,082 | -0.027 | -0.029..-0.025 | 0.00% (0.35) |

Candidate (top R with move t > 2): **S2b**.

## Validation (2024-07..2025-09)
S2b **-0.124R** (CI -0.231..-0.009), S2c -0.065R, S3a -0.135R. **Stage 1 FAIL**; nothing goes to stage 2.

## Why the train result did not hold
- Unconditional 10-day return of these 20 stocks in train was +0.69%. After S2b call signals it was +0.88%, so only about
  +0.2% was timing; the rest was market drift. After put signals stocks rose (-0.98% in the put direction).
- 80% of S2b trades were calls on today's large caps in a 2016-2024 bull market: drift plus survivorship bias.
- In validation (a weaker market for large caps) the calls lost (-0.49% vs +0.20% unconditional).
- Modelled IV = 1.1 x realized vol is likely generous to buyers (real implied vol usually carries a premium over realized).

## Reading
Longer holds with monthly rollover did better than intraday (intraday is negative, as for the index), but the
improvement was market beta, not a signal. No variant passes; stage 2 (real option prices) is not needed for these.
