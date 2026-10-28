# Monthly hedged option selling with a 5% profit target: pre-registration DRAFT

Status: **draft, not frozen**. It is frozen (renamed, committed) before any monthly option data is downloaded.

## Idea (owner's rule)
Sell Nifty **monthly** options as a hedged (defined-risk) position and close it once profit reaches **5% of capital
employed**. Rationale: option sellers earn an insurance premium over time; the earlier same-day test was close to
break-even before slippage, and holding for weeks collects much more time decay.

## Mechanics (all variants)
- Near monthly expiry. Entry at 10:00 on the entry day; one position at a time; next entry only after the previous exit.
- Strikes from the ATM strike K0 at the 09:45 bar close (50-pt steps), in strike offsets (1 offset = 50 pts):
  `fly`: sell CE/PE K0, buy CE K0+6, PE K0-6 | `condor_n`: sell K0+/-2, buy K0+/-8 | `condor_w`: sell K0+/-4, buy K0+/-10.
- Fills: sell at bid, buy at ask when real quotes exist; on historical bars: price -/+ max(1%, 0.5 pt) per leg per side.
- **Capital employed** = maximum loss of the position (width - credit) x quantity. Real NSE/Dhan margin for a hedged
  position is close to this but includes extra exposure margin [VERIFY with Dhan]; using max loss makes the 5% target
  slightly easier to reach than with true margin.
- **Profit target (owner's rule):** close when mark-to-market P&L after estimated exit costs >= 5% of capital employed,
  checked at every 15-min bar close; fill at the next bar's open.
- Always exit by 15:15 on the trading day **before** expiry (no expiry-day holding, consistent with the standing choice).
- Size: lots so that capital employed <= 20% of equity [TUNE]; results also reported in R = net / capital employed.
- Leg prices outside the fetched ATM-10..ATM+10 band are modelled (Black-76, nearest strike IV); the share is reported.

## Variants (3 x 2 x 2 = 12)
| Factor | Levels |
|---|---|
| Structure | fly, condor_n, condor_w |
| Entry day | first trading day after the previous monthly expiry (about 4 weeks left); the 2nd Tuesday after it (about 2 weeks left) |
| Stop | none (defined risk; hold to target or the day-before-expiry exit); loss >= 10% of capital employed |

## Selection rule
1. Train 2021-11..2024-06 (about 31 cycles), validation 2024-07..2025-09 (about 15 cycles); test sealed.
2. Eligible: >= 25 train trades. Rank by train mean R; top 3 to validation; confirmed only if the top one has
   validation mean R > 0 and 90% bootstrap CI lower bound > 0. Also reported: worst cycle, max drawdown, how often
   the 5% target was hit, and the loss on target-missed cycles.
3. Power warning stated now: one trade per month gives about 31 + 15 trades; only a large effect can be confirmed.
   A pass would need forward shadow confirmation before any real money.

## Data needed
Dhan expired options, expiryFlag MONTH, near contract, ATM-10..ATM+10, calls and puts, 15-min, 2021-11..2025-09:
about 2,500 requests. Blocked from the cloud environment since 2026-10-27 (DH-905 on every expired-options request
while other endpoints work).
