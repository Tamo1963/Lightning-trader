"""Lightning Trader shadow dashboard (read-only). Run: streamlit run app/dashboard.py
Reads the shadow SQLite audit DB. Places no orders and holds no credentials."""
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "shadow" / "live.sqlite"

st.set_page_config(page_title="Lightning Trader - Shadow", layout="wide")
st.title("Lightning Trader · shadow testing")
st.caption("Paper only. No orders are placed. Strategies shown are forward-tracked hypotheses that failed backtests.")

dbs = sorted((ROOT / "data" / "shadow").glob("*.sqlite")) if (ROOT / "data" / "shadow").exists() else []
default = DEFAULT_DB if DEFAULT_DB in dbs else (dbs[0] if dbs else None)
arg = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else None
choice = st.sidebar.selectbox("Audit database", [str(x) for x in dbs], index=[str(x) for x in dbs].index(str(default)) if default else 0) if dbs else None
path = arg or choice
if not path or not Path(path).exists():
    st.warning("No shadow database yet. Start `python scripts/run_shadow.py --live` or run a `--replay`.")
    st.stop()

con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def q(sql):
    return pd.read_sql_query(sql, con)


hb = q("SELECT * FROM heartbeat ORDER BY ts DESC LIMIT 50")
trades = q("SELECT * FROM paper_trades")
cands = q("SELECT * FROM candidates")
gates = q("SELECT * FROM gates")
jev = q("SELECT id, requested_at, latency_ms, model, decision, detail_json, error FROM jev_calls")

tab = st.tabs(["Status", "Candidates & gates", "Paper trades", "Spreads", "Jev"])

with tab[0]:
    c1, c2, c3, c4 = st.columns(4)
    last = q("SELECT MAX(ts) ts FROM bars")["ts"].iat[0]
    c1.metric("Last bar", last or "-")
    c2.metric("Last heartbeat", hb["ts"].iat[0] if len(hb) else "-")
    c3.metric("Open paper positions", int((trades["status"] == "OPEN").sum()) if len(trades) else 0)
    errors = hb[hb["status"] != "OK"] if len(hb) else hb
    c4.metric("Errors (last 50 beats)", len(errors))
    if len(errors):
        st.error("Recent errors"); st.dataframe(errors, width="stretch")
    st.subheader("Heartbeat"); st.dataframe(hb, width="stretch", height=250)

with tab[1]:
    if cands.empty:
        st.info("No candidates yet.")
    else:
        st.dataframe(cands.groupby(["strategy", "status"]).size().rename("n").reset_index(), width="stretch")
        g = gates.pivot_table(index="candidate_id", columns="gate", values="reason", aggfunc="first")
        view = cands.set_index("id")[["strategy", "side", "decision_ts", "status"]].join(g)
        st.dataframe(view.sort_values("decision_ts", ascending=False), width="stretch")

with tab[2]:
    if trades.empty:
        st.info("No paper trades yet.")
    else:
        closed = trades[trades["status"] == "CLOSED"].copy()
        closed["exit_ts"] = pd.to_datetime(closed["exit_ts"], utc=True)
        rows = []
        for (s, label), sub in [((s, "A (all candidates)"), g) for s, g in closed.groupby("strategy")] + \
                               [((s, "A+J (Jev approved)"), g[g["jev_decision"] == "APPROVE"]) for s, g in closed.groupby("strategy")]:
            if len(sub):
                rows.append({"strategy": s, "variant": label, "n": len(sub), "win_rate": round((sub["net"] > 0).mean(), 3),
                             "mean_R": round(sub["net_r"].mean(), 3), "net_inr": round(sub["net"].sum()),
                             "net_at_mid_inr": round(sub["net_mid"].sum()), "spread_cost_inr": round(sub["net_mid"].sum() - sub["net"].sum())})
        st.subheader("Summary (A vs A+J on identical candidates)")
        st.dataframe(pd.DataFrame(rows), width="stretch")
        st.caption("A+J needs a Jev key; until then every Jev decision is UNAVAILABLE and A+J is empty.")
        eq = closed.sort_values("exit_ts").groupby("strategy")["net"].cumsum()
        chart = closed.sort_values("exit_ts").assign(cum_net=eq).pivot_table(index="exit_ts", columns="strategy", values="cum_net").ffill()
        st.subheader("Cumulative paper P&L (INR)"); st.line_chart(chart)
        st.subheader("All paper trades"); st.dataframe(trades.sort_values("entry_ts", ascending=False), width="stretch")

with tab[3]:
    qq = q("SELECT ts, strike, side, bid, ask, spot FROM quotes WHERE bid > 0 AND ask > 0")
    if qq.empty:
        st.info("No quotes yet.")
    else:
        qq["mid"] = (qq["bid"] + qq["ask"]) / 2
        qq["spread_pct"] = 100 * (qq["ask"] - qq["bid"]) / qq["mid"]
        qq["moneyness"] = ((qq["strike"] - qq["spot"]) / 50).round().astype(int)
        s = qq.groupby(["side", "moneyness"])["spread_pct"].median().unstack("side")
        st.subheader("Median bid-ask spread, % of mid, by strikes from spot")
        st.dataframe(s.round(2), width="stretch")
        st.caption("Backtests assumed 1% slippage per side (about a 2% round-trip spread). Real data here replaces that guess. "
                   "Replay databases use a synthetic spread, so only live data is meaningful.")

with tab[4]:
    if jev.empty:
        st.info("No Jev calls yet.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Calls", len(jev))
        c2.metric("Errors / unavailable", int(jev["decision"].isin(["UNAVAILABLE"]).sum() + jev["error"].notna().sum()))
        c3.metric("Median latency ms", int(jev["latency_ms"].median()) if jev["latency_ms"].notna().any() else 0)
        side = cands.set_index("id")["side"]
        jj = jev.assign(side=jev["id"].map(side))
        st.subheader("Decisions by candidate direction (buy-bias check)")
        st.dataframe(jj.groupby(["side", "decision"]).size().unstack(fill_value=0), width="stretch")
        jj["reason"] = jj["detail_json"].map(lambda x: (json.loads(x) or {}).get("reason") if x else None)
        st.dataframe(jj[["requested_at", "side", "decision", "reason", "latency_ms", "error"]].sort_values("requested_at", ascending=False),
                     width="stretch")
