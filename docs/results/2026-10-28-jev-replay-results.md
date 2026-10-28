# Jev historical replay: results (2026-10-28)

Protocol: `2026-10-28-jev-replay-preregistration.md`. Run by the owner with jev-1.13.0 on 51 distinct word-only states
(400 baseline-A trades). 0 API errors.

| Split | Candidates | Approved | Mean R all | Mean R approved | Mean R rejected | Approved - all, 90% CI | Rank corr (Jev side prob, R) |
|---|---|---|---|---|---|---|---|
| Train | 279 | 126 (45%) | -0.100 | -0.113 | -0.090 | -0.089 .. +0.066 | -0.004 |
| Validation | 121 | 61 (50%) | -0.094 | -0.109 | -0.079 | -0.075 .. +0.045 | -0.000 |

**Verdict: FAIL** (criterion 1 fails on both splits; approval rate was within 35-90%).

## Reading
- Jev's approvals do not pick better trades: approved trades did slightly *worse* than rejected ones in both splits,
  and its direction probability has zero rank correlation with outcomes.
- It is not a rubber stamp (45-50% approved), but its selectivity carries no information about these trades.
- **Run-to-run variation:** two runs on the same 51 states approved the same number of trades (187) but gave different
  rejection reasons (entry-extended 129 vs 90, stand-aside 19 vs 69, direction-mismatch 65 vs 54). On borderline
  states the reason, and possibly the stand-aside probability, is not stable; the clear-cut spike state was stable.
  Max rotation spread 0.12-0.14 (option order matters somewhat on these states).

## Consequence (as pre-registered)
Jev adds nothing as a filter on the baseline candidates. Shadow mode keeps logging Jev verdicts, but nothing is built on them.
