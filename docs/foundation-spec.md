# Foundation Spec v0.1 (draft, to be frozen before any test run)

Anything marked **[VERIFY]** is an external fact that must be confirmed in Phase 0.
Anything marked **[TUNE]** is a placeholder default that must be fixed on validation data, then frozen.

## 1. Scope and design decisions

| Decision | v1 choice | Reason |
|---|---|---|
| Instruments | Nifty 50 and Bank Nifty index options (buying only) | Stocks are monthly-only and thinner; expand after validation |
| Signal horizon | Single: 30 min [TUNE], intraday only | Mixing 15-60 min and swing horizons was inconsistent |
| Indicator source | **Front-month futures** for VWAP, VWMA, volume; spot for price levels | Spot indices have no volume |
| Candles | Completed 15-min candles only; entry at next bar open | No look-ahead |
| Outcome label | Premium P&L, triple barrier (target / stop / time stop) | We trade premium, not the index |
| Contract specs | Config, refreshed from Dhan instrument master | Expiry days, weeklies, lot sizes change [VERIFY] |
| Runtime | Worker process (data, signals, orders, exits) + DB + thin Streamlit UI | Streamlit reruns cannot host an always-on exit loop |
| Jev | One call per candidate, after all deterministic gates | Fewer correlated opinions, lower latency |

Monthly RSI and weekly RSI change are a **static directional bias**, not intraday signals.
Define precisely: monthly RSI(14) on the last *completed* monthly candle; weekly RSI change =
RSI(14) of last completed weekly candle minus the one before it. (Revisit if the monthly bias is
effectively constant over the test window; then it adds nothing and should be dropped.)

## 2. Gates (all mandatory, evaluated cheap to expensive, first failure rejects and logs)

| Gate | Owner | Question | Output |
|---|---|---|---|
| G1 Tradability | Code | Data fresh and complete? Regime ok (ADX, ATR bounds)? No event flag? Inside time window? Not expiry-day gamma? | PASS / FAIL + reason |
| G2 Candidate | Code | Do the baseline rules fire? CALL: monthly RSI>50, weekly RSI change>0, 15m close > VWAP, VWMA, SuperTrend. PUT: mirror. | BUY_CALL / BUY_PUT / NONE |
| G3 Statistical | Code | Calibrated P(favorable premium outcome) above threshold, and above the opposite side? | PASS / FAIL + probabilities |
| G4 Jev | Jev (typed questions) | Direction match, entry quality, thesis support, averaged over option orders | APPROVE / REJECT (fail closed) |
| G5 Risk | Code | Reward/risk, costs, size, spread, liquidity, exposure, daily loss, duplicates | APPROVE / REJECT + reason |

Rules:
- Jev timeout, error, invalid schema or low-quality response = REJECT (fail closed).
- Jev is used as a bounded classifier of supplied labelled evidence; its output is never an order, a size or a stop.
- Jev confidence is **not** a win probability and is never used in sizing or EV.
- G3 probability is shown to Jev only in variant `A+S+J` (see section 7); in `A+J` Jev is blind to it.
- G3 and G4 disagreement: NO TRADE.
- Stops, targets and exits never depend on a new Jev response.

## 3. Features (deterministic, computed once, versioned)

Trend: EMA 20/50/100/200, ADX(14), SuperTrend. Momentum: RSI(14), MACD, ROC. Volatility: ATR(14),
realized vol, opening range. Structure: swing highs/lows, distance to support/resistance.
Participation (futures): relative volume, breadth. Derivatives: OI change, PCR, IV, bid-ask spread.
Extension: (close - VWAP) / ATR. Keep the set small; every added feature raises overfitting risk.

Data freshness: last tick age <= 5 s [TUNE]; candle must be closed; no gaps in the last N bars.
Event calendar: maintained file (RBI, Budget, major data, expiry); a flag, not an LLM judgement.

## 4. Jev contract (revised after reading TypeSafe/AIML docs and a live-trading write-up)

Jev is **not an LLM**. It is a "System One" decision model: input is a `state` (string/JSON) plus typed
questions (`choice`, `score`, `noul`); output is a chosen option, a probability per option and a
confidence. There is no prose, no reasoning and no reason codes. Consequences:

- No policy text or rubric prompt. Each option carries a short `criteria` definition (`schemas/jev_questions.json`).
- State contains **labels, not raw numbers** (e.g. "RSI: strong", "price: stretched above value"), no dates, tickers, absolute levels or free text.
- Every choice question is sent in **all cyclic option orders** and averaged; the rotation spread is logged (option order alone moved ~26% of answers by >=0.10 in one independent test).
- Every question includes an abstain option (`stand_aside`, `unclear`).
- Model pinned (`jev-1.13.0`), question and state-builder hash stored on every call.
- **Confidence is not used for sizing or as a win probability.** In an independent crypto test, calls at >=0.95 were right less often than calls <0.70. Jev outputs are inputs to a rule fitted on validation data and frozen; its raw confidence is never trusted.
- Jev agreed with the LLM it was compared with on 112/117 calls (it echoes what is in the state). Therefore the state must include information the baseline rules do not already encode (derivatives, breadth, structure, time-of-day), and the ablation must show the approve rate is not ~100%.
- Jev is **never used for exits or position management** (in that test it answered "hold" every time).

G4 rule (draft [TUNE]): APPROVE iff averaged `direction` matches the candidate side, `stand_aside` probability is below a
threshold, `entry_quality` = `good_entry` wins, and `thesis_supported` is above a threshold; thresholds fitted on validation, then frozen.
Any error, timeout, or high rotation spread: REJECT.

Provisional: exact response field names are confirmed in the Phase 0 spike.

## 5. Deterministic risk and execution rules (G5)

Defaults live in `config/risk.defaults.yaml`. Principles:

- One reward/risk rule, defined on **option premium**: expected reward / max loss >= 2.0 after
  brokerage, taxes, exchange charges and modelled slippage (current charge schedule in config [VERIFY]).
- Position size = floor(risk_budget / (premium_risk_per_lot)). If one lot exceeds the budget: skip.
- Stop and target set at entry. Time stop at horizon. Forced square-off before close.
- Daily loss limit blocks new entries only; exits stay active.
- Duplicate-signal and duplicate-order protection via idempotency key.
- Emergency exit and kill switch run in the worker, independent of Jev and the UI.
- Reconcile orders, fills and positions with DhanHQ every N seconds; mismatch halts new entries.
- Token: entered manually in the UI, held in worker memory only, never logged. On expiry, entries stop and exits continue.
- Static IP / algo tagging / retail-algo rules: confirm with Dhan and current SEBI/NSE circulars [VERIFY].

## 6. Audit

Every candidate is recorded, including rejected ones, with the inputs and outputs of every gate,
raw Jev request/response, versions (code, features, model, Jev, config), and the outcome. Rejected
candidates are **still paper-traded** so counterfactual outcomes exist. See `schemas/audit.sql`.
Any decision must be reproducible from the log.

## 7. Backtest and validation protocol

Variants run on identical candidates and identical execution assumptions:

| Variant | Description |
|---|---|
| A | Baseline rules + risk gate |
| A+S | A + statistical gate |
| A+J | A + Jev gate (blind to stats) |
| A+S+J | A + stats + Jev (Jev sees stats) |

Data: chronological train / validation / untouched test; walk-forward for the stats model. Thresholds
chosen on validation, frozen, then evaluated once on test. Option P&L is simulated from historical
premiums where available (else modelled with delta/theta/IV, flagged as lower fidelity) [VERIFY data].

Costs: brokerage, STT, exchange and SEBI charges, GST, stamp duty, plus slippage as a fraction of
the bid-ask spread. Same assumptions across all variants.

Staging:
1. Replay (smoke test only: an LLM may have seen the historical period; do not use as proof).
2. **Forward shadow** (the real verdict): live data, no orders, all four variants logged in parallel.
3. Paper trading with simulated fills and exits.
4. Pilot: 1 lot, manual approval per trade, kill switch tested.

Sample size: state the minimum detectable effect before starting. Roughly 400 paired trades detect a
0.2R improvement; roughly 1,500 detect 0.1R (sigma ~1R). Expect 6-12 months of shadow data at 1-3
candidates per day per index. Count independent days and regimes, not just trades.

## 8. Acceptance criteria (pre-registered; edit only before the first test run)

Phase gates:
1. **Baseline:** variant A net expectancy per trade > 0 after costs on validation and test. If not, redesign rules; do not proceed to Jev.
2. **Stats model:** calibrated (reliability plot, Brier score better than climatology); A+S beats A on validation with a CI excluding 0.
3. **Jev adds value:** on the untouched forward sample, paired bootstrap of net R per candidate for A+J vs A has a 90% CI lower bound > 0, max drawdown not worse, and >= 35% [TUNE] of candidates retained.
4. **Process integrity:** zero look-ahead findings; 100% decisions reproducible; Jev error rate <= 2% [TUNE] (all fail closed).
5. **Pilot entry:** positive net expectancy after real costs, profit factor >= 1.3 [TUNE], drawdown within limit, across at least two regimes.

Metrics: net expectancy (R and INR) per trade, profit factor, max drawdown, Sharpe/Sortino on daily P&L,
trade count, avoided losers, missed winners, approve rate by direction.

## 9. Implementation sequence

| Phase | Work | Exit |
|---|---|---|
| 0 | Feasibility spikes: Jev API (determinism, latency, versioning, data terms), Dhan data (futures history, expired options, rate limits, token life, static IP), regulatory check | All verified or design changed |
| 1 | Freeze this spec | Signed-off, tagged `spec-v1` |
| 2 | Data layer, indicators, option P&L simulator, variant A backtest | Gate 1 |
| 3 | Statistical model and calibration | Gate 2 |
| 4 | Jev harness, logging, consistency and mirror tests, anonymized replay | Jev tests pass |
| 5 | Forward shadow, four variants, thin Streamlit monitor | Gates 3, 4 |
| 6 | Paper trading with execution simulation and reconciliation | Matches shadow |
| 7 | Controlled pilot | Gate 5 |

## 10. Open questions for the owner

- Direct TypeSafe or AI/ML API gateway for the key you hold (Phase 0).
- Is the monthly-RSI bias worth keeping if it is constant across the test window?
- Preferred time window and expiry handling (avoid expiry day, or trade it separately?).
