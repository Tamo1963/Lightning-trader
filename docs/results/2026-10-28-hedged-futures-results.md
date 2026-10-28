# Futures with option hedges: results (2026-10-28)

Protocol: `2026-10-28-hedged-futures-preregistration.md` (committed before download). NSE bhavcopy 2016-01..2025-09,
22 underlyings, monthly cycles (~100 train, 13-14 validation). Tables: `2026-10-28-hedged-futures-*.csv`. Test sealed.

## Liquidity screen ("can be used consistently")
13 of 22 qualify (3% and 5% OTM next-month options traded on >= 90% of train roll days): AXISBANK, BHARTIARTL, HDFCBANK,
ICICIBANK, INFY, ITC, LT, M&M, RELIANCE, SBIN, SUNPHARMA, TATASTEEL, TCS.
Did not qualify: BANKNIFTY (0.70), NIFTY (0.88), BAJFINANCE, HINDUNILVR, KOTAKBANK, MARUTI, NTPC, TITAN, ULTRACEMCO.
For Bank Nifty and Nifty the next-month 3-5% OTM monthly options often did not trade on the roll day, mainly in the
earlier years when weekly options dominated; they are liquid today, but not consistently over 2016-2024.

## Verdicts (pre-registered rules, qualifying underlyings)
| Overlay | Worth it | Sharpe better than buy-and-hold (train / val) | Median return change, pp/yr (train / val) | Median max-drawdown ratio (train / val) |
|---|---|---|---|---|
| **C5 covered call, 5% OTM** | **6 / 13** | 10 / 13, 11 / 13 | +0.3 / +5.2 | 0.83 / 0.81 |
| C3 covered call, 3% OTM | 4 / 13 | 9 / 13, 11 / 13 | -1.4 / +5.4 | 0.83 / 0.73 |
| P3 protective put, 3% OTM | 0 / 13 | 0 / 13, 1 / 13 | -7.8 / -5.7 | 0.85 / 0.91 |
| P5 protective put, 5% OTM | 0 / 13 | 0 / 13, 1 / 13 | -7.1 / -5.1 | 0.87 / 1.00 |

C5 "worth it" (train, validation and >= 70% of train years): BHARTIARTL, HDFCBANK, INFY, ITC, SUNPHARMA, TCS.
C3: BHARTIARTL, INFY, ITC, SUNPHARMA.

## Reading
- **Covered calls (5% OTM) are the first broadly consistent positive result in this project:** on most liquid stocks
  they kept roughly the same return in train while cutting volatility and drawdowns by ~15-20%, so risk-adjusted
  return improved in 10 of 13 stocks in train and 11 of 13 in validation. This matches the well-documented tendency of
  out-of-the-money index and stock calls to be overpriced. The strict rule (incl. >= 70% of individual years) passes 6.
- Validation was a weak period for several stocks; covered calls lose less when a stock falls (the premium cushions it),
  which flatters them in validation. Train is the fairer read: about flat return, lower risk.
- **Protective puts are not worth it:** they cost about 5-8 percentage points a year and barely reduce maximum drawdown,
  because monthly puts protect against a single month's crash (they paid in March 2020) but not against slow declines.
- Survivorship bias (today's large caps) inflates buy-and-hold itself; the overlay-vs-baseline comparison is less affected.
- Not modelled: margin/collateral interest, taxes, and early-exercise/assignment (Indian stock options are European).

## Data checks
- Corporate actions: cycles with a >30% futures jump excluded (e.g. Bajaj Finance splits 2016 and 2025). The cycle right
  after the 2016 Bajaj Finance split still has inconsistent option prices (P5 -103%); Bajaj Finance is excluded by the
  liquidity screen, and a scan of all qualifying underlyings found no similar artifacts: every overlay-vs-baseline gap
  above 25% is a real event (March 2020 crash, large 2017-2021 rallies).
