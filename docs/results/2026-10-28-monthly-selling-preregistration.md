# Monthly hedged option selling with a 5% profit target: pre-registration (FROZEN 2026-10-28)

Frozen before any option data for this study was downloaded. Owner confirmed the defaults.

## Idea (owner's rule)
Sell Nifty **monthly** options as a defined-risk position and close it once profit reaches **5% of capital employed**.
Rationale: option sellers earn an insurance premium over time; holding for weeks collects much more decay than the
earlier same-day test (which was close to break-even before slippage).

## Data
NSE daily F&O bhavcopy (end-of-day, every strike and expiry; old format until 2024-07-05, UDiFF format after),
Nifty index options of the **monthly** expiry (the last expiry date in each calendar month, as listed in the files).
Spot close: Dhan daily Nifty 50. Bhavcopy has no bid/ask.

## Mechanics (all variants)
- Decisions and fills at the **daily close** (entry, target, stop and exit), using the bhavcopy close price.
- ATM strike K0 = spot close rounded to 50. Offsets in 50-pt steps:
  `fly`: sell CE/PE K0, buy CE K0+300, PE K0-300 | `condor_n`: sell K0+/-100, buy K0+/-400 | `condor_w`: sell K0+/-200, buy K0+/-500.
  If a wing strike is not listed, use the nearest listed strike further out; if a short strike is not listed, skip the cycle.
- Fills: sell at close - s, buy at close + s, s = max(1% of price, 0.5 pt), per leg per side. Charges per leg from
  `config/costs.yaml` (8 orders). Zero-volume leg-days are counted and reported (their close may be stale).
- **Capital employed** = maximum loss of the position = (width - credit) x quantity (owner's default; true margin is a
  little higher [VERIFY with Dhan]).
- **Target (owner's rule):** close at the first daily close where P&L after estimated exit slippage and charges >= 5% of capital employed.
- **Exit** at the close of the last trading day before expiry if neither target nor stop hit (no expiry-day holding).
- One position at a time. Lots: capital employed <= 20% of equity (equity starts at INR 10,00,000; lot size by date).
- Results in R = net P&L / capital employed, and in INR.

## Variants (3 x 2 x 2 = 12)
| Factor | Levels |
|---|---|
| Structure | fly, condor_n, condor_w |
| Entry day | `early`: first trading day after the previous monthly expiry; `mid`: first trading day with <= 14 calendar days to expiry |
| Stop | `none`; `stop10`: close when P&L <= -10% of capital employed |

## Selection rule
1. Train 2016-01-01..2024-06-30 (about 100 cycles), validation 2024-07-01..2025-09-30 (about 15 cycles); test (2025-10
   onward) not downloaded and sealed.
2. Eligible: >= 60 train trades. Rank by train mean R; top 3 to validation; **confirmed** only if the top one has
   validation mean R > 0 and 90% bootstrap CI (resampling cycles) lower bound > 0.
3. Also reported: target hit rate, mean loss when the target is missed, worst cycle (INR), max drawdown, zero-volume share.
4. Power warning: validation has about 15 cycles, so only a large effect can be confirmed there. A pass still needs
   forward shadow confirmation before real money.
