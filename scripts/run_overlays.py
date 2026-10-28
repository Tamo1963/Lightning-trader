"""Pre-registered hedged-futures overlay study (docs/results/2026-10-28-hedged-futures-preregistration.md)."""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lightning.config import load_params
from lightning.overlays import perf, run_symbol

TRAIN, VAL = (date(2016, 1, 1), date(2024, 6, 30)), (date(2024, 7, 1), date(2025, 9, 30))
LOTS = {"NIFTY": 65, "BANKNIFTY": 30}


def main():
    p = load_params()
    stocks = yaml.safe_load((ROOT / "config" / "stocks.yaml").read_text())["stocks"]
    files = sorted((ROOT / "data" / "nse" / "multi").glob("*.csv.gz"))
    cols = ["symbol", "kind", "date", "expiry", "strike", "opt", "close", "volume"]
    df = pd.concat([pd.read_csv(f, usecols=cols) for f in files], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["expiry"] = pd.to_datetime(df["expiry"]).dt.date
    print(f"files {len(files)}, rows {len(df)}, {df['date'].min()} .. {df['date'].max()}")
    out = ROOT / "data" / "out" / "overlays"; out.mkdir(parents=True, exist_ok=True)
    summary, verdicts = [], []
    for sym, g in df.groupby("symbol"):
        cyc = run_symbol(g, LOTS.get(sym) or stocks[sym]["lot"], p.costs)
        if cyc.empty:
            continue
        cyc.to_csv(out / f"{sym}.csv", index=False)
        n_ca = int(cyc["corp_action"].sum())
        cyc = cyc[~cyc["corp_action"]]
        tr = cyc[(cyc["d_in"] >= TRAIN[0]) & (cyc["d_in"] <= TRAIN[1])]
        va = cyc[(cyc["d_in"] >= VAL[0]) & (cyc["d_in"] <= VAL[1])]
        liq = float(np.mean([tr[f"{v}_traded"].mean() for v in ("P3", "P5", "C3", "C5")]))
        liq_min = float(min(tr[f"{v}_traded"].mean() for v in ("P3", "P5", "C3", "C5")))
        qualifies = liq_min >= 0.90
        pf = {(s, v): perf(x[v]) for s, x in (("train", tr), ("val", va)) for v in ("B0", "P3", "P5", "C3", "C5")}
        years = tr.assign(y=pd.to_datetime(tr["d_out"]).dt.year).groupby("y")
        row = {"symbol": sym, "cycles_train": len(tr), "cycles_val": len(va), "corp_action_excluded": n_ca,
               "liquidity_min": round(liq_min, 3), "qualifies": qualifies}
        for s in ("train", "val"):
            for v in ("B0", "P3", "P5", "C3", "C5"):
                row[f"{s}_{v}_ret"] = round(pf[(s, v)].get("ann_ret", np.nan), 4)
                row[f"{s}_{v}_sharpe"] = round(pf[(s, v)].get("sharpe", np.nan), 3)
                row[f"{s}_{v}_mdd"] = round(pf[(s, v)].get("max_dd", np.nan), 4)
        summary.append(row)
        def m(split, var, key):  # missing metric (too few cycles) -> NaN, which fails every comparison
            return pf[(split, var)].get(key, np.nan)

        for v in ("P3", "P5", "C3", "C5"):
            if v.startswith("C"):
                yr_share = float(np.mean([perf(y[v]).get("sharpe", -9) > perf(y["B0"]).get("sharpe", -9) for _, y in years]))
                ok = all(m(s, v, "sharpe") > m(s, "B0", "sharpe") for s in ("train", "val")) and yr_share >= 0.70
                extra = {"train_years_better": round(yr_share, 2)}
            else:
                ok = all(m(s, v, "max_dd") <= 0.7 * m(s, "B0", "max_dd") and
                         m(s, "B0", "ann_ret") - m(s, v, "ann_ret") <= 0.03 for s in ("train", "val"))
                extra = {}
            verdicts.append({"symbol": sym, "overlay": v, "qualifies": qualifies, "worth_it": bool(ok), **extra})
    S, V = pd.DataFrame(summary), pd.DataFrame(verdicts)
    S.to_csv(out / "summary.csv", index=False); V.to_csv(out / "verdicts.csv", index=False)
    show = ["symbol", "qualifies", "liquidity_min", "cycles_train", "cycles_val"] + \
           [f"{s}_{v}_{m}" for s in ("train", "val") for v in ("B0", "P5", "C3") for m in ("ret", "sharpe", "mdd")]
    pd.set_option("display.width", 250)
    print(S[show].to_string(index=False))
    q = V[V["qualifies"]]
    print("\nWORTH IT (qualifying underlyings only):")
    print(q.groupby("overlay")["worth_it"].agg(["sum", "count"]).rename(columns={"sum": "worth_it", "count": "qualifying"}))
    print("\nwhere worth it:", q[q["worth_it"]][["symbol", "overlay"]].values.tolist())


if __name__ == "__main__":
    main()
