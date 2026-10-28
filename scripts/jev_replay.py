"""Pre-registered Jev historical replay (docs/results/2026-10-28-jev-replay-preregistration.md).

Run on a machine with JEV_API_KEY set:  python scripts/jev_replay.py
Calls Jev once per distinct state (about 51 calls), then scores the pre-registered rule against backtest outcomes.
Writes data/raw/jev_replay_results.csv and prints a key-free summary to paste back."""
import asyncio
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lightning.live.jev import aggregate, api_key, decide, rotated_questions


async def ask_all(states, model):
    from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy
    client = AsyncTypeSafeClient(api_key=api_key(), model=model, timeout=10.0, retry=RetryPolicy(max_retries=2))
    questions, _ = rotated_questions()
    sem = asyncio.Semaphore(4)

    async def one(s):
        async with sem:
            try:
                r = await client.system_one(state=json.loads(s), questions=questions)
                return s, (r.model_dump() if hasattr(r, "model_dump") else r), None
            except Exception as e:  # noqa: BLE001
                return s, None, f"{type(e).__name__}: {str(e)[:200]}"
    return await asyncio.gather(*[one(s) for s in states])


def boot_diff(df, n=4000, seed=0):
    """90% CI of mean(approved) - mean(all), resampling decision days."""
    rng = np.random.default_rng(seed)
    days = df["day"].unique()
    g = {d: x for d, x in df.groupby("day")}
    diffs = []
    for _ in range(n):
        s = pd.concat([g[d] for d in rng.choice(days, len(days))])
        a = s[s["decision"] == "APPROVE"]["net_r"]
        if len(a):
            diffs.append(a.mean() - s["net_r"].mean())
    return float(np.quantile(diffs, 0.05)), float(np.quantile(diffs, 0.95))


def main():
    if not api_key():
        sys.exit("set JEV_API_KEY")
    cfg = yaml.safe_load((ROOT / "config" / "shadow.yaml").read_text())["jev"]
    c = pd.read_csv(ROOT / "research" / "jev_replay" / "candidates.csv")
    _, groups = rotated_questions()
    results = asyncio.run(ask_all(sorted(c["state_json"].unique()), cfg["model"]))
    by_state, errors = {}, 0
    for s, raw, err in results:
        side = 1 if json.loads(s)["candidate"] == "buy call" else -1
        if err:
            errors += 1
            by_state[s] = {"decision": "REJECT", "reason": "ERROR", "p_side": np.nan, "spread": np.nan, "error": err}
            continue
        agg = aggregate(raw, groups)
        dec, why = decide(agg, side, cfg["rule"])
        key = "call_favorable" if side == 1 else "put_favorable"
        by_state[s] = {"decision": dec, "reason": why, "p_side": agg["direction"]["probs"].get(key, np.nan),
                       "spread": max(a["spread"] for a in agg.values()), "error": None}
    c = c.join(c["state_json"].map(by_state).apply(pd.Series))
    c["day"] = c["decision_ts"].str[:10]
    out = ROOT / "data" / "raw"; out.mkdir(parents=True, exist_ok=True)
    c.drop(columns=["state_json"]).to_csv(out / "jev_replay_results.csv", index=False)

    print(f"Jev calls: {len(results)} distinct states, errors: {errors}")
    print("reasons:", c["reason"].value_counts().to_dict())
    verdict = True
    for split in ("train", "validation"):
        s = c[c["split"] == split]
        a, r = s[s["decision"] == "APPROVE"], s[s["decision"] != "APPROVE"]
        rate = len(a) / len(s)
        lo, hi = boot_diff(s) if len(a) else (float("nan"), float("nan"))
        rho = s["p_side"].rank().corr(s["net_r"].rank()) if s["p_side"].nunique() > 1 else float("nan")
        ok = len(a) > 0 and a["net_r"].mean() > s["net_r"].mean() and lo > 0 and 0.35 <= rate <= 0.90
        verdict &= ok
        print(f"\n[{split}] candidates {len(s)}, approved {len(a)} ({rate:.0%})")
        print(f"  mean R: all {s['net_r'].mean():+.3f} | approved {a['net_r'].mean() if len(a) else float('nan'):+.3f} | "
              f"rejected {r['net_r'].mean() if len(r) else float('nan'):+.3f}")
        print(f"  approved - all: 90% CI [{lo:+.3f}, {hi:+.3f}]; rank corr(Jev side prob, R) {rho:+.3f}; "
              f"max rotation spread {s['spread'].max():.3f}")
        print(f"  criteria met: {ok}")
    print(f"\nPRE-REGISTERED VERDICT: {'PASS' if verdict else 'FAIL'}")


if __name__ == "__main__":
    main()
