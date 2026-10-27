# Defined-risk option selling: pre-registration (committed BEFORE implementation and any run)

Hypothesis: intraday Nifty moves are usually small and tend to revert (both earlier studies), so a hedged short-premium
position opened in the morning and closed by 15:15 earns time decay on most days, and the wings cap the loss on trend days.

## Structure and mechanics (all variants)
- Near weekly expiry, at least 2 calendar days to expiry; expiry days blocked (as configured). One position per day.
- Strikes from the near-expiry ATM strike K0 at the decision bar close:
  - `fly` (iron butterfly): sell CE K0 + PE K0; buy CE K0+150 + PE K0-150 (width 150).
  - `condor` (iron condor): sell CE K0+50 + PE K0-50; buy CE K0+150 + PE K0-150 (width 100).
- Entry at the open of the entry bar. Fills: sells at price x (1 - s), buys at price x (1 + s), s = max(1% of price, 0.5 pt) per leg per side.
- Credit C = sum(short fills) - sum(long fills). Risk per unit R_u = width - C. Reject if C <= 0 or R_u <= 0.
- Size: lots = floor(1% of equity / (R_u x lot)); also width x qty <= 30% of capital (margin proxy). Reject if < 1 lot.
- Monitoring on bar closes. Position value V = shorts - longs at closes.
  - Stop (variant `stop_tp`): close when V - C >= 0.5 x R_u. Take profit: close when V <= 0.5 x C. Exit fill at the NEXT bar open.
  - Always: square-off at the close of the 15:00-15:15 bar.
- Charges per leg as in `config/costs.yaml` (8 orders per trade). R = net P&L / (R_u x qty).
- A leg whose strike is outside the fetched ATM-3..ATM+3 band at a bar is priced with Black-76 using spot, time to
  expiry and the IV of the nearest fetched strike on the same side. The share of such modelled leg-bars is reported.

## Factors (2 x 2 x 2 x 2 = 16 variants)
| Factor | Levels |
|---|---|
| Structure | `fly`, `condor` |
| Entry time | 10:00 (decision bar 09:45), 12:00 (decision bar 11:45) |
| Exit rule | `time` (square-off only), `stop_tp` (stop at half of max loss, take profit at half of credit, plus square-off) |
| Day filter | `none`; `iv_high`: previous day's closing near-ATM IV above the 67th percentile of the trailing 60 sessions |

## Selection rule (fixed now)
1. Run all 16 on train (2021-11-01..2024-06-30). Eligible: >= 100 train trades.
2. Rank by train net expectancy (R); top-ranked = candidate; ranks 2-3 reported.
3. Run only the top 3 on validation (2024-07-01..2025-09-30).
4. Confirmed only if the candidate's validation expectancy > 0 AND 90% day-clustered bootstrap CI lower bound > 0.
   Also reported: worst single-day loss, max drawdown, and profit factor.
5. Test split sealed.

Caveats stated now: (i) intraday only, no overnight/expiry holding; (ii) bar-close monitoring cannot see intra-bar
spikes, but loss is capped by the wings; (iii) real margin (SPAN + exposure) is not modelled beyond the proxy.
