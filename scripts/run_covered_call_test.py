"""One-shot sealed test of the 5% covered call (docs/results/2026-10-28-covered-call-TEST-preregistration.md)."""
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

UNIVERSE = ["AXISBANK", "BHARTIARTL", "HDFCBANK", "ICICIBANK", "INFY", "ITC", "LT", "M&M", "RELIANCE", "SBIN",
            "SUNPHARMA", "TATASTEEL", "TCS"]
T0, T1 = date(2025, 10, 1), date(2026, 10, 31)


def main():
    p = load_params()
    stocks = yaml.safe_load((ROOT / "config" / "stocks.yaml").read_text())["stocks"]
    files = sorted(f for f in (ROOT / "data" / "nse" / "multi").glob("*.csv.gz") if f.name[:8] >= "20250801")
    cols = ["symbol", "kind", "date", "expiry", "strike", "opt", "close", "volume"]
    df = pd.concat([pd.read_csv(f, usecols=cols) for f in files], ignore_index=True)
    df = df[df["symbol"].isin(UNIVERSE)]
    df["date"], df["expiry"] = pd.to_datetime(df["date"]).dt.date, pd.to_datetime(df["expiry"]).dt.date
    rows, pooled = [], []
    for sym in UNIVERSE:
        c = run_symbol(df[df["symbol"] == sym], stocks[sym]["lot"], p.costs)
        c = c[(c["expiry"] >= T0) & (c["expiry"] <= T1)]
        n_ca = int(c["corp_action"].sum())
        c = c[~c["corp_action"]]
        b, x = perf(c["B0"]), perf(c["C5"])
        rows.append({"symbol": sym, "cycles": len(c), "corp_action_excluded": n_ca,
                     "B0_ret": round(b["ann_ret"], 4), "C5_ret": round(x["ann_ret"], 4),
                     "B0_sharpe": round(b["sharpe"], 3), "C5_sharpe": round(x["sharpe"], 3),
                     "B0_mdd": round(b["max_dd"], 4), "C5_mdd": round(x["max_dd"], 4),
                     "sharpe_better": x["sharpe"] > b["sharpe"]})
        pooled.append(c[["expiry", "B0", "C5"]].assign(symbol=sym))
    R = pd.DataFrame(rows)
    out = ROOT / "data" / "out" / "covered_call_test"; out.mkdir(parents=True, exist_ok=True)
    R.to_csv(out / "per_stock.csv", index=False)
    P = pd.concat(pooled).groupby("expiry")[["B0", "C5"]].mean()
    pd.set_option("display.width", 200)
    print(R.to_string(index=False))
    n_better = int(R["sharpe_better"].sum())
    d_ret = float((R["C5_ret"] - R["B0_ret"]).median())
    dd_ratio = float((R["C5_mdd"] / R["B0_mdd"]).median())
    pb, px = perf(P["B0"]), perf(P["C5"])
    print(f"\npooled equal-weight portfolio ({len(P)} cycles): B0 ret {pb['ann_ret']:+.2%} sharpe {pb['sharpe']:.2f} mdd {pb['max_dd']:.2%} | "
          f"C5 ret {px['ann_ret']:+.2%} sharpe {px['sharpe']:.2f} mdd {px['max_dd']:.2%}")
    c1, c2, c3 = n_better >= 9, d_ret >= -0.02, dd_ratio <= 1.0
    print(f"\n1. Sharpe better in {n_better}/13 (need >= 9): {c1}")
    print(f"2. median return change {100 * d_ret:+.2f} pp/yr (need >= -2): {c2}")
    print(f"3. median drawdown ratio {dd_ratio:.2f} (need <= 1.0): {c3}")
    print(f"\nSEALED TEST VERDICT: {'PASS' if c1 and c2 and c3 else 'FAIL'}")


if __name__ == "__main__":
    main()
