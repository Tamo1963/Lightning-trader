# Execution Plan v0.3

Inputs: capital INR 10,00,000; max risk per trade 2% (INR 20,000); Jev access via an API key.
Companion: `foundation-spec.md` (gates, protocol, acceptance criteria), `config/risk.defaults.yaml`.
Items marked **[VERIFY]** are external facts not yet confirmed.

## 1. What changed after researching Jev

Sources: TypeSafe/AI-ML API model page and one independent 17-day live-trading write-up (single author, small sample).

| Finding | Effect on the plan |
|---|---|
| Jev is a non-LLM typed decision model (choice / score / noul questions, probabilities per option, confidence). No prose or reasons. | Dropped the rubric-prompt and `reason_code` design. Questions with per-option criteria instead. |
| Strong sensitivity to option order; numbers are a weak spot; untrusted text can steer it. | Rotate and average options; state is labels only; no free text. |
| Confidence ran **backwards** on crypto direction (>=0.95 right 32%, <0.70 right 57%). Real-money result: 15 trades, -4.5R. | Confidence is never a size or win probability. Thresholds are fitted on our own validation data. Jev is a veto, so the system works even if Jev adds nothing. |
| It echoed the LLM on 112/117 calls (same inputs, same mistakes). | Give Jev information the rules do not encode; test that it is not a rubber stamp. |
| Cheap (about INR 0.02 per question set) and fast (about 0.1-0.5 s). | Large historical replays are affordable, so development is not limited by API cost. |
| Version 1.14 already out; alias `typesafe/jev` can float. | Pin `jev-1.13.0`; re-validate before any upgrade. |

Honest prior: there is no published evidence that Jev improves trade selection. The plan is built so that
a negative result is cheap, early and unambiguous.

## 2. Capital and risk framework

2% of INR 10,00,000 = **INR 20,000 hard cap per trade**. That cap is a ceiling, not a target.

| Stage | Risk per trade | Entry condition |
|---|---|---|
| Shadow / paper | 1.0% simulated | Phases 5-6 |
| Pilot 1 (first 100 live trades) | 0.5% (INR 5,000) | Phase 7 gate |
| Pilot 2 | 1.0% (INR 10,000) | Pilot 1: positive net expectancy, drawdown inside limit, no rule breaches |
| Full | up to 2.0% (INR 20,000) | Pilot 2 criteria; never above the cap |

Why a ladder: an unproven edge at 2% means ten straight stops cost about 18% of capital.

Account-level limits (code, G5): daily loss 3% (must exceed one full-risk stop), weekly 6%, halt at 10% drawdown
from peak equity until manual review, 5 consecutive losses pause entries, max 2 open positions, max 3 entries/day,
premium outlay per position at most 10% of capital.

**Sizing (long options, loss = premium stop):** lots = floor(risk budget / (lot size x premium stop distance)),
then capped by the outlay limit. Illustration only, not a market reading: Nifty lot 65 [VERIFY], premium 150,
stop 30% = INR 45 x 65 = INR 2,925 per lot, so INR 5,000 risk gives 1 lot and INR 20,000 gives 6 lots
(outlay about INR 58,500). Real stops will gap in thin strikes, so size on modelled slippage, not the stop alone.
If one lot exceeds the budget: no trade.

## 3. Architecture

```
DhanHQ data -> worker: features -> G1 tradability -> G2 candidate -> G3 stats -> G4 Jev -> G5 risk -> orders
                         |                                                   (all outcomes logged, rejected ones paper-traded)
                         v
                      database (audit) <- Streamlit UI (monitor, paper console, reports, token entry)
```

- **Worker** (separate process): data, signals, Jev calls, orders, exits, kill switch. Runs without the UI.
- **Streamlit**: display and controls only. Token entered manually, passed to the worker in memory, never logged.
- **Secrets:** `JEV_API_KEY` from env / secret store (`.env` is git-ignored, template in `.env.example`). Do not paste the key into chats, commits or logs; if it has already been shared anywhere, rotate it.
- **Data:** indicators on front-month futures (spot index has no volume); completed 15-min candles; entry at next bar open.

## 4. Jev integration design

- Three questions (`schemas/jev_questions.json`): `direction` (choice), `entry_quality` (choice), `thesis_supported` (noul).
- Labelled state: trend, momentum, stretch from value, structure, participation, derivatives (OI/PCR/IV direction as words), breadth, session phase, event flag. Statistical probabilities appear only as words in variant A+S+J.
- Each choice question sent in all 3 option rotations; averaged; rotation spread logged; large spread = reject.
- Pre-flight tests before any evidence is collected: repeat-call stability, option-order sensitivity, mirror test (flip bullish/bearish state), prompt-perturbation test, approve-rate by direction, approve-rate overall (a rubber stamp approves >90%).
- G4 thresholds fitted on validation, frozen. Jev is never used for exits.

## 5. Phased plan

| Phase | Weeks | Deliverables | Exit gate (all required) |
|---|---|---|---|
| 0 Feasibility | 1 | (a) Jev spike: call with your key, store raw responses, confirm field names, endpoint (direct vs gateway), limits, data terms. (b) Dhan: futures and options history, expired-options availability, rate limits, token lifetime, static-IP/algo rules. (c) Charges schedule and lot sizes. (d) Broker/regulatory check for algo use. | Every [VERIFY] item resolved or the design changed. Go/no-go recorded. |
| 1 Freeze spec | 1 | Tag `spec-v1`: labels, window, thresholds' search ranges, metrics, acceptance criteria. | Written, tagged, no edits afterwards except via a logged amendment. |
| 2 Data and baseline | 2-3 | Ingestion, feature pipeline (no look-ahead tests), option P&L simulator with costs and slippage, variant A backtest. | Net expectancy per trade > 0 after costs on validation **and** test; else redesign rules, stop here. |
| 3 Statistical model | 2-3 | Walk-forward model, calibration report, A vs A+S. | Calibrated; A+S beats A with CI excluding 0. If not, drop S and proceed with A+J only. |
| 4 Jev harness | 2 | State builder, question runner, logging, pre-flight tests, anonymised historical replay (development evidence only). | Pre-flight tests pass; approve rate not a rubber stamp; thresholds fitted on validation and frozen. |
| 5 Forward shadow | 12+ | Live data, no orders; A, A+S, A+J, A+S+J logged in parallel; every candidate paper-traded. Streamlit monitor. | Pre-registered Jev test (below) on untouched forward sample, plus >=2 regimes seen. |
| 6 Paper trading | 4 | Simulated fills and exits through the real order path with reconciliation. | Results within tolerance of shadow; zero reconciliation breaks; kill switch drill passed. |
| 7 Pilot | 8+ | 1 lot, manual per-trade approval at 0.5% risk, daily review. | Pilot 1 criteria, then ladder per section 2. |

Parallel from week 1: audit schema, config loader, secrets handling, kill-switch and emergency-exit module, CI with unit tests for G5.

## 6. Testing the Jev decision (pre-registered)

- Compare A vs A+J (and A+S+J) on identical candidates; rejected candidates are paper-traded for counterfactuals.
- Primary metric: net R per candidate, paired bootstrap, **90% CI lower bound > 0** for the improvement; secondary: drawdown not worse, profit factor, >=35% of candidates retained, approve rate by direction within +/-10 points.
- Sample size: about 400 paired candidates to see a 0.2R gain, about 1,500 for 0.1R. Historical replay can supply development volume; forward shadow is the confirmation.
- Verdicts: **Jev adds value** -> keep. **No measurable difference** -> keep only if it costs nothing and never removes winners disproportionately; otherwise remove (system runs A or A+S). **Harmful** -> remove.
- Caution on replay: model training data is undisclosed, so past dates may not be clean. Anonymise state, and trust forward results over replay.

## 7. Kill criteria and failure handling

| Condition | Action |
|---|---|
| Baseline A negative after costs | Stop; redesign rules before any Jev work |
| Jev error rate >2% or latency beyond timeout | Fail closed (no entries); investigate |
| Order/position mismatch with Dhan | Halt entries; manual reconcile |
| Data stale or incomplete | No new entries; exits continue |
| Daily/weekly/drawdown limit hit | Halt per limits; review before resuming |
| Jev version change or provider outage | Revert to pinned version; re-run pre-flight tests |
| Pilot drawdown beyond pre-set bound | Back to paper; post-mortem |

## 8. Decisions recorded (v0.3)

| Question | Answer | Consequence |
|---|---|---|
| Jev key source | TypeSafe directly | Use `typesafe-sdk` (pinned `0.7.5`); spike script `scripts/jev_spike.py`. Gateway not needed. |
| Dhan data | Paid data plan | Phase 0 still confirms exactly what it covers (see checklist below). |
| Scope | Nifty first, stocks included | See section 9. |
| Expiry day | Default: no entries | `block_expiry_day_entries: true` |

Phase 0 Dhan checklist: intraday history depth for index futures and stock futures; expired-options history (strikes, OI, IV);
live option chain and market depth; websocket limits; token lifetime; static-IP and order-API requirements; rate limits.

## 9. Including stocks

Stocks are in scope but **not pooled with the index**. Reasons: stock options are monthly only, spreads are wider, lot sizes
and liquidity vary widely, and single names have earnings, corporate actions and F&O ban periods that indices do not.

- **Universe:** F&O stocks filtered by liquidity (option spread, OI, volume, futures turnover), starting from Nifty 50 constituents. List is config, reviewed monthly.
- **Extra G1 checks for stocks:** earnings/board-meeting date within the holding window, F&O ban list, corporate action, circuit/price-band proximity, stock-vs-index relative strength as a label for Jev.
- **Extra G5 checks:** stricter spread and OI limits, smaller outlay cap per stock (default 5% of capital), max 1 position per stock and at most 2 stock positions at once.
- **Validation:** Nifty is the primary study. Stocks run as a separate study (own baseline A, own acceptance gates) and share only code. Cross-sectional pooling is allowed for the stats model only if per-stock results are consistent. More names gives more candidates, which helps the sample-size problem, but more variants also raises the false-discovery risk: all stock tests count toward the same multiple-testing budget and use the same frozen thresholds.
- **Sequencing:** Nifty goes through Phases 2-5 first. Stock data ingestion and the universe filter are built in Phase 2 in parallel; stock shadow testing starts when the Nifty Jev pre-flight tests (Phase 4) pass, so Jev behaviour is understood before it scales.
- Live trading on stocks is not enabled until the stock study passes its own Phase 5 gate.
