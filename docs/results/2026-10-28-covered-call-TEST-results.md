# Sealed test of the 5% covered call: results (2026-10-28)

Protocol: `2026-10-28-covered-call-TEST-preregistration.md` (committed before the test data was downloaded).
Test cycles: expiries Oct 2025 .. Oct 2026, 13 per stock, 13 liquid stocks. Table: `2026-10-28-covered-call-TEST-per-stock.csv`.

## Verdict: PASS (all three pre-registered criteria)
1. Sharpe better than buy-and-hold in **9 / 13** stocks (needed >= 9). Better: BHARTIARTL, HDFCBANK, ICICIBANK, INFY, ITC,
   M&M, RELIANCE, SUNPHARMA, TATASTEEL. Worse: AXISBANK, LT, SBIN, TCS.
2. Median annualised return change **+3.1 pp** (needed >= -2).
3. Median max-drawdown ratio **0.86** (needed <= 1.0).
Equal-weight portfolio of the 13: buy-and-hold -11.0%/yr, Sharpe -0.71, max drawdown 18.2%; covered call -8.8%/yr,
Sharpe -0.62, max drawdown 15.0%.

## Checks
- Every futures cycle matches the stock's cash price move within 3% (no hidden corporate actions). The falls are real
  (cash: HDFCBANK -28%, ITC -36%, INFY -19%, M&M -17%, RELIANCE -13%).
- Futures trailed cash by 5-7% a year: the cost of carry. A real account earns interest on the collateral, which this
  test leaves out for both strategies equally.

## Reading
- It passed, but in a falling year for most of these stocks, which is the easiest environment for covered calls (the
  premium cushions losses and few rallies are capped). Absolute returns were still negative: this is risk reduction
  on a long position, not a way to make money in a falling market.
- The margin is thin (9 of 13 against a threshold of 9) and each stock has only 13 test months.
- Together with train (2016-2024) and validation (2024-2025), the evidence is consistent: on liquid large caps a 5% OTM
  monthly covered call keeps roughly the same return with ~15-20% lower drawdowns.

## Practical sizing (owner capital INR 10 lakh)
One lot of futures per stock is INR 4.4-9.7 lakh notional (13 stocks: about INR 82 lakh). Fully collateralised, INR 10
lakh covers only one or two stocks. Exchange margins (roughly 15-25%) would allow more, but that is leverage, which
these results do not evaluate.
