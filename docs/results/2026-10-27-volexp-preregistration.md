# Volatility-expansion family: pre-registration (committed BEFORE implementation and any run)

Hypothesis: on Nifty, a breakout of the opening range continues far enough for an ATM option buyer to profit,
especially after compression (quiet prior day) or when options are cheap (low IV), i.e. when a volatility
expansion is more likely and not yet priced.

## Signal (all variants)
- Opening range (OR) = high/low of the first K bars of the session (from 09:15).
- First 15-min bar after the OR that **closes** above OR high -> BUY CALL; closes below OR low -> BUY PUT.
- At most one candidate per day (the first breakout, either side). Decision bar close must be <= 13:00.
- No RSI/VWAP/SuperTrend rules. Expiry-day block, min 2 DTE, costs, slippage, risk 1%, one position,
  premium stop 30% and target solved for 2.0R net: all unchanged. Drawdown halt off (research).

## Factors (2 x 3 x 2 = 12 variants)
| Factor | Levels |
|---|---|
| OR length K | 30 min (2 bars), 60 min (4 bars) |
| Day filter | `none`; `compression`: previous day's range < 0.75 x median range of the 20 days before it; `low_iv`: previous day's closing near-ATM IV (mean of call and put, last bar, IV>0 only) below the 33rd percentile of the trailing 60 trading days |
| Exit horizon | 60 min (4 bars), EOD (square-off 15:15) |

All filters use only data known before the session opens.

## Selection rule (fixed now)
1. Run all 12 on train (2021-11-01..2024-06-30). Eligible: >= 60 train trades.
2. Rank by train net expectancy (R); top-ranked = candidate; ranks 2-3 reported.
3. Run only the top 3 on validation (2024-07-01..2025-09-30).
4. Confirmed only if the candidate's validation expectancy > 0 AND 90% day-clustered bootstrap CI lower bound > 0.
5. Secondary (reported, not used for selection): index move in the trade direction from entry to horizon, in ATR
   units; an ATM option buyer needs roughly +0.3 ATR or more for the trade to be viable.
6. Test split sealed. Same data limitation as before (next-expiry options incomplete -> NO_OPTION_DATA).
