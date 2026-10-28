# Jev historical replay: pre-registration (committed BEFORE any Jev call on historical states)

Question: does Jev's verdict separate better baseline trades from worse ones, or does it approve almost everything?

## Data
- Candidates: every **traded** baseline-A candidate (edge entry, 30-min horizon, full HTF filter; research mode,
  real Dhan option prices) in train (2021-11..2024-06) and validation (2024-07..2025-09). Test stays sealed.
- File: `research/jev_replay/candidates.csv`: id, split, side, decision time, Jev state (words only: no dates,
  tickers or numbers), and the backtest outcome (net R). Outcomes are never sent to Jev.
- Model `jev-1.13.0`, questions `schemas/jev_questions.json` (version q-0.1), every choice in all option orders, averaged.

## Decision rule (fixed now; the draft in `config/shadow.yaml`, not tuned)
APPROVE iff the averaged direction choice is the candidate side, stand_aside <= 0.40, the entry-quality choice is
`good_entry`, and thesis_supported >= 0.50. Any API error = REJECT.

## Success criteria (all required, on train AND on validation separately)
1. Mean net R of approved minus mean net R of all candidates > 0, with the 90% day-clustered bootstrap CI lower bound > 0.
2. Approval rate between 35% and 90% (below 35%: too few trades; above 90%: rubber stamp).
Also reported, not used for the verdict: mean R of rejected candidates, rotation spread, and the rank correlation between
Jev's direction probability and net R (the independent study found it negative).

## Interpretation fixed now
- Fails 1 or approves > 90%: Jev adds nothing as a filter on these candidates. Shadow keeps recording it, but nothing is built on it.
- Passes both splits: the rule becomes the A+J candidate for forward shadow testing; the sealed test split is
  still not used until the shadow evaluation is pre-registered.

## Note added at export (before any Jev call)
The 400 candidates map to only 51 distinct word-only states (the labels are coarse), so Jev's verdict can take at
most 51 distinct values here, and the replay needs about 51 calls. This limits how finely Jev can separate trades;
it is a property of the state design being tested, not a change to the protocol.
