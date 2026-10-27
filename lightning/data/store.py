from __future__ import annotations

from pathlib import Path

import pandas as pd

IST = "Asia/Kolkata"
SESSION_START, SESSION_END = "09:15", "15:30"


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index_label="ts")


def load_intraday(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["ts"], index_col="ts")
    df.index = pd.DatetimeIndex(df.index)
    df.index = df.index.tz_localize(IST) if df.index.tz is None else df.index.tz_convert(IST)
    return df.sort_index()


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["ts"], index_col="ts").sort_index()
    df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
    return df


def validate_intraday(df: pd.DataFrame, minutes: int = 15) -> list[str]:
    """Data-quality checks. Empty list = pass. Run before any backtest; also confirms bar-START timestamps."""
    problems = []
    if not df.index.is_monotonic_increasing:
        problems.append("index not sorted")
    if df.index.has_duplicates:
        problems.append("duplicate timestamps")
    if df[["open", "high", "low", "close"]].isna().any().any():
        problems.append("NaN prices")
    if ((df["high"] < df[["open", "close"]].max(axis=1)) | (df["low"] > df[["open", "close"]].min(axis=1))).any():
        problems.append("OHLC inconsistent")
    firsts = df.groupby(df.index.normalize()).apply(lambda g: g.index[0].strftime("%H:%M"))
    if (firsts != SESSION_START).any():
        problems.append(f"{int((firsts != SESSION_START).sum())} sessions do not start at {SESSION_START} (bar-start convention? gaps?)")
    if (df.index.strftime("%H:%M") >= SESSION_END).any():
        problems.append("bars at/after session end")
    per_day = df.groupby(df.index.normalize()).size()
    expected = (15 * 60 + 30 - (9 * 60 + 15)) // minutes
    short = int((per_day < expected).sum())
    if short:
        problems.append(f"{short} sessions with fewer than {expected} bars (gaps or half days)")
    return problems


def stitch_contracts(frames: list[tuple[pd.Timestamp, pd.DataFrame]], roll_days_before: int = 2) -> pd.DataFrame:
    """Continuous front-month series from per-contract frames [(expiry_date, df), ...]. NOT back-adjusted
    (real levels are needed for strike selection). The first bars after each roll are flagged `post_roll`
    so signals can skip them."""
    parts, prev_end = [], None
    for expiry, df in sorted(frames, key=lambda x: x[0]):
        cut = (pd.Timestamp(expiry).tz_localize(IST) if pd.Timestamp(expiry).tz is None else pd.Timestamp(expiry)) \
            - pd.Timedelta(days=roll_days_before)
        seg = df[df.index < cut]
        if prev_end is not None:
            seg = seg[seg.index >= prev_end]
        if seg.empty:
            continue
        seg = seg.copy()
        seg["post_roll"] = False
        if prev_end is not None:
            seg.iloc[0, seg.columns.get_loc("post_roll")] = True
        parts.append(seg)
        prev_end = cut
    return pd.concat(parts) if parts else pd.DataFrame()
