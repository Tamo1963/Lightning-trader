# Redesign grid: pre-registration (written and committed BEFORE any variant was run)

Question: does any of three redesigns of the baseline rules give positive net expectancy after costs?

## Variants (2 x 4 x 3 = 24)
| Factor | Levels | Definition |
|---|---|---|
| Entry (redesign a) | `edge` (baseline) | first bar on which all rules become true |
| | `pullback` | trend state true (SuperTrend up, close > VWMA, plus the HTF filter) AND the bar's low touches/undercuts session VWAP AND it closes back above VWAP. Puts mirrored. |
| Horizon (redesign b) | 30, 60, 120 min, EOD | time stop after 2 / 4 / 8 bars, or square-off at 15:15 |
| HTF filter (redesign c) | `full` (baseline) | monthly RSI vs 50 AND weekly RSI change sign |
| | `no_monthly` | weekly RSI change only |
| | `none` | 15-min rules only |

Everything else unchanged: premium stop 30%, target solved for 2.0R net, slippage 1%/side, costs, risk 1%,
entry window 09:30-14:30 decisions, expiry-day block, min 2 DTE, one position at a time, drawdown halt off (research).

## Selection rule (fixed now)
1. Run all 24 on **train** (2021-11-01..2024-06-30). Eligible: >= 100 train trades.
2. Rank eligible variants by train expectancy (R). The **top-ranked variant is the candidate**; ranks 2-3 are reported for context.
3. Run **only the top 3** on **validation** (2024-07-01..2025-09-30).
4. Confirmed only if the candidate's validation expectancy > 0 **and** its 90% day-clustered bootstrap CI lower bound > 0.
5. Test split stays sealed. With 24 variants tried, a single positive train result is weak evidence; validation decides.

Known limitation: next-expiry option data is incomplete (Dhan quota), so day-before-expiry candidates are rejected
as NO_OPTION_DATA in every variant equally.
