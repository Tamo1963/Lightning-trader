"""Stock options study, stage 1 runner (pre-registered: docs/results/2026-10-27-stocks-preregistration.md)."""
import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lightning.config import load_params
from lightning.data import store
from lightning.features import build_features
from lightning.metrics import cluster_bootstrap_ci
from lightning.signals import BAR, generate
from lightning.stock_study import (IV_MULT, cluster_t, daily_signals, model_option_r, monthly_expiries,
                                   pick_monthly, realized_vol)

IST = "Asia/Kolkata"
ROOT = Path(__file__).resolve().parent.parent


def ts(d, hh, mm):
    return pd.Timestamp(d).tz_localize(IST) + pd.Timedelta(hours=hh, minutes=mm)


def summarize(name, t, sp):
    lo, hi = pd.Timestamp(sp["from"]).tz_localize(IST), pd.Timestamp(sp["to"]).tz_localize(IST) + pd.Timedelta(days=1)
    t = t[(t["entry_ts"] >= lo) & (t["entry_ts"] < hi)]
    if len(t) < 3:
        return {"variant": name, "n": len(t), "mean_r": float("-inf")}
    day = t["entry_ts"].dt.normalize()
    ci = cluster_bootstrap_ci(t["r"].to_numpy(), day.to_numpy())
    return {"variant": name, "n": len(t), "dates": int(day.nunique()), "calls": int((t.side == 1).sum()),
            "puts": int((t.side == -1).sum()), "mean_r": round(t["r"].mean(), 4), "ci90_lo": round(ci[0], 4),
            "ci90_hi": round(ci[1], 4), "win": round((t["r"] > 0).mean(), 3), "median_r": round(t["r"].median(), 4),
            "move_mean_pct": round(100 * t["move"].mean(), 3), "move_t": round(cluster_t(t["move"], day), 2)}


def main():
    cfg = yaml.safe_load((ROOT / "config" / "stocks.yaml").read_text())
    p = load_params()
    data = {}
    for sym in cfg["stocks"]:
        dd = ROOT / "data" / "stocks" / sym
        if (dd / "daily.csv").exists():
            data[sym] = {"daily": store.load_daily(dd / "daily.csv"),
                         "m15": store.load_intraday(dd / "15m.csv") if (dd / "15m.csv").exists() else None}
    print("stocks loaded:", len(data))
    all_days = sorted(set().union(*[set(v["daily"].index.date) for v in data.values()]))
    expiries = monthly_expiries(all_days, p.expiry_schedule)
    trades = {k: [] for k in ["S1a_intraday_30m", "S1b_intraday_EOD", "S2a_daily_5d", "S2b_daily_10d",
                              "S2c_daily_20d", "S3a_mom_12_1", "S3b_mom_6_1"]}

    for sym, v in data.items():
        s, daily = cfg["stocks"][sym], v["daily"]
        rv = realized_vol(daily["close"]) * IV_MULT
        def opt(s_in, s_out, side, t_in, t_out):
            iv = rv.get(t_in.tz_localize(None).normalize(), np.nan)
            if not np.isfinite(iv) or iv <= 0:
                return None
            e = pick_monthly(expiries, t_in.date(), (t_out.date() - t_in.date()).days + 7)
            return model_option_r(s_in, s_out, side, t_in, t_out, e, iv, s["strike_step"], s["lot"], p.costs)

        # S2: daily rules, hold H trading days, one position per stock
        sig = daily_signals(daily)
        for name, h in (("S2a_daily_5d", 5), ("S2b_daily_10d", 10), ("S2c_daily_20d", 20)):
            free = -1
            for i in np.flatnonzero(sig.to_numpy() != 0):
                e, x = i + 1, i + h
                if x >= len(daily) or e <= free:
                    continue
                side = int(sig.iat[i])
                t_in, t_out = ts(daily.index[e], 9, 15), ts(daily.index[x], 15, 30)
                r = opt(daily["open"].iat[e], daily["close"].iat[x], side, t_in, t_out)
                if r:
                    trades[name].append({"sym": sym, "entry_ts": t_in, "exit_ts": t_out, "side": side, **r})
                    free = x

        # S1: intraday baseline rules on the stock's own 15-min bars
        if v["m15"] is not None:
            m15, _ = store.clean_intraday(v["m15"])
            f = build_features(m15, daily, p)
            cands = generate(f, p)
            pos = {t: k for k, t in enumerate(f.index)}
            dayarr = f.index.date
            for name, hb in (("S1a_intraday_30m", 2), ("S1b_intraday_EOD", 99)):
                free = -1
                for t0, row in cands.iterrows():
                    i = pos[t0]; e = i + 1
                    if e >= len(f) or dayarr[e] != dayarr[i] or e <= free:
                        continue
                    x = e
                    while x + 1 < len(f) and dayarr[x + 1] == dayarr[e] and x < e + hb - 1 and (f.index[x] + BAR).time() < p.square_off:
                        x += 1
                    t_in, t_out = f.index[e], f.index[x] + BAR
                    r = opt(f["open"].iat[e], f["close"].iat[x], int(row["side"]), t_in, t_out)
                    if r:
                        trades[name].append({"sym": sym, "entry_ts": t_in, "exit_ts": t_out, "side": int(row["side"]), **r})
                        free = x

    # S3: cross-sectional momentum, monthly roll
    cal = pd.DatetimeIndex(all_days)
    closes = pd.DataFrame({s: v["daily"]["close"] for s, v in data.items()}).reindex(cal).ffill(limit=5)
    opens = pd.DataFrame({s: v["daily"]["open"] for s, v in data.items()}).reindex(cal)
    firsts = [k for k in range(1, len(cal)) if cal[k].month != cal[k - 1].month]
    for name, lb in (("S3a_mom_12_1", 252), ("S3b_mom_6_1", 126)):
        for a, b in zip(firsts[:-1], firsts[1:]):
            if a - lb < 0:
                continue
            mom = (closes.iloc[a - 21] / closes.iloc[a - lb] - 1).dropna()
            if len(mom) < 10:
                continue
            ranked = mom.sort_values()
            picks = [(s, 1) for s in ranked.index[-3:]] + [(s, -1) for s in ranked.index[:3]]
            x = b - 1
            for sym, side in picks:
                s_in, s_out = opens[sym].iat[a], closes[sym].iat[x]
                if not (np.isfinite(s_in) and np.isfinite(s_out)):
                    continue
                t_in, t_out = ts(cal[a], 9, 15), ts(cal[x], 15, 30)
                cs = cfg["stocks"][sym]
                rv = realized_vol(data[sym]["daily"]["close"]) * IV_MULT
                iv = rv.get(cal[a], np.nan)
                if not np.isfinite(iv):
                    continue
                e = pick_monthly(expiries, cal[a].date(), (cal[x].date() - cal[a].date()).days + 7)
                r = model_option_r(s_in, s_out, side, t_in, t_out, e, iv, cs["strike_step"], cs["lot"], p.costs)
                trades[name].append({"sym": sym, "entry_ts": t_in, "exit_ts": t_out, "side": side, **r})

    out = ROOT / "data" / "out" / "stocks"; out.mkdir(parents=True, exist_ok=True)
    T = {k: pd.DataFrame(v) for k, v in trades.items()}
    for k, t in T.items():
        t.to_csv(out / f"{k}.csv", index=False)
    sp = cfg["splits"]
    train = pd.DataFrame([summarize(k, t, sp["train"] if k.startswith("S1") else sp["train_daily"]) for k, t in T.items()])
    train = train.sort_values("mean_r", ascending=False)
    train.to_csv(out / "train.csv", index=False)
    print("\nTRAIN (ranked by mean modelled R):"); print(train.to_string(index=False))
    elig = train[train["n"] >= 100]
    cand = elig[elig["move_t"] > 2]
    if cand.empty:
        print("\nNo eligible variant has a train stock-move t-stat > 2: stage 1 stops, no candidate (per pre-registration).")
        return
    top = elig.head(3)["variant"].tolist()
    c_name = cand.iloc[0]["variant"]
    val = pd.DataFrame([summarize(k, T[k], sp["validation"]) for k in dict.fromkeys([c_name] + top)])
    val.to_csv(out / "validation.csv", index=False)
    print(f"\nCandidate: {c_name}\nVALIDATION:"); print(val.to_string(index=False))
    c = val[val["variant"] == c_name].iloc[0]
    print(f"\nStage 1 {'PASS' if c['mean_r'] > 0 and c['ci90_lo'] > 0 else 'FAIL'} for {c_name}")


if __name__ == "__main__":
    main()
