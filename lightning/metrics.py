from __future__ import annotations

import numpy as np
import pandas as pd


def summarize(trades: pd.DataFrame, capital: float, n_boot: int = 2000, seed: int = 0) -> dict:
    if trades.empty:
        return {"n_trades": 0}
    net, r = trades["net"], trades["net_r"]
    wins, losses = net[net > 0], net[net < 0]
    eq = capital + net.cumsum()
    dd = (eq.cummax() - eq)
    day = trades["entry_ts"].dt.normalize()
    daily = net.groupby(day).sum() / capital
    lo, hi = cluster_bootstrap_ci(r.to_numpy(), day.to_numpy(), n_boot, seed)
    return {
        "n_trades": len(trades),
        "n_days": int(day.nunique()),
        "win_rate": float((net > 0).mean()),
        "expectancy_r": float(r.mean()),
        "expectancy_r_ci90": (lo, hi),
        "expectancy_inr": float(net.mean()),
        "total_pnl_inr": float(net.sum()),
        "total_costs_inr": float(trades["costs"].sum()),
        "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) else float("inf"),
        "avg_win_r": float(r[net > 0].mean()) if len(wins) else 0.0,
        "avg_loss_r": float(r[net < 0].mean()) if len(losses) else 0.0,
        "max_drawdown_inr": float(dd.max()),
        "max_drawdown_pct": float((dd / eq.cummax()).max() * 100),
        "daily_sharpe_ann": float(daily.mean() / daily.std(ddof=1) * np.sqrt(250)) if len(daily) > 2 and daily.std(ddof=1) > 0 else float("nan"),
        "exit_reasons": trades["exit_reason"].value_counts().to_dict(),
    }


def cluster_bootstrap_ci(values: np.ndarray, clusters: np.ndarray, n_boot: int = 2000, seed: int = 0,
                         level: float = 0.90):
    """CI of the mean, resampling whole days (trades within a day are correlated)."""
    rng = np.random.default_rng(seed)
    groups = [values[clusters == c] for c in np.unique(clusters)]
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        means[b] = np.concatenate([groups[k] for k in pick]).mean()
    a = (1 - level) / 2
    return float(np.quantile(means, a)), float(np.quantile(means, 1 - a))
