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


def offset_label(k: int) -> str:
    return "ATM" if k == 0 else f"ATM{k:+d}"


def load_options(data_dir: Path) -> pd.DataFrame:
    """Concatenate data_dir/options/slot{S}_{CE|PE}_{offset}.csv into one long table."""
    parts = []
    for path in sorted((data_dir / "options").glob("slot*_*_*.csv")):
        slot, side, off = path.stem.split("_")
        df = pd.read_csv(path, parse_dates=["ts"])
        if df.empty:
            continue
        df["ts"] = pd.DatetimeIndex(df["ts"]).tz_convert(IST) if pd.DatetimeIndex(df["ts"]).tz is not None \
            else pd.DatetimeIndex(df["ts"]).tz_localize(IST)
        df["slot"], df["side"], df["offset"] = int(slot[4:]), side, int(off)
        parts.append(df)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def attach_option_volume(spot: pd.DataFrame, opt: pd.DataFrame, slot: int = 0) -> pd.DataFrame:
    """Spot index has no volume: use total near-expiry option volume (all fetched strikes, CE+PE) per bar
    as the participation weight for VWAP/VWMA. The live system must use the same proxy."""
    v = opt[opt["slot"] == slot].groupby("ts")["volume"].sum()
    out = spot.copy()
    out["volume"] = v.reindex(out.index).fillna(0).to_numpy()
    return out


def regular_sessions(df: pd.DataFrame, min_bars: int = 20) -> pd.Index:
    """Dates of normal weekday sessions: first bar 09:15 and at least `min_bars` bars."""
    day = df.index.normalize()
    g = df.groupby(day)
    first = g.apply(lambda x: x.index[0].strftime("%H:%M"))
    n = g.size()
    ok = (first == SESSION_START) & (n >= min_bars) & (first.index.weekday < 5)
    return first.index[ok]


def calendar_days(df: pd.DataFrame) -> list:
    """Exchange trading days for the EXPIRY calendar: weekday sessions that start before noon. Excludes
    Muhurat/evening special sessions (which happen on holidays), keeps days with a late-starting data gap."""
    g = df.groupby(df.index.normalize())
    first = g.apply(lambda x: x.index[0].time())
    keep = [d.date() for d, t in first.items() if d.weekday() < 5 and t.hour < 12]
    return keep


def clean_intraday(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Keep regular sessions and bars 09:15..15:15 (bar start); repair high/low that do not bracket open/close."""
    out = df[df.index.strftime("%H:%M") < SESSION_END]
    days = regular_sessions(out)
    dropped_days = sorted(set(out.index.normalize()) - set(days))
    out = out[out.index.normalize().isin(days)].copy()
    hi, lo = out[["open", "high", "close"]].max(axis=1), out[["open", "low", "close"]].min(axis=1)
    repaired = int(((hi != out["high"]) | (lo != out["low"])).sum())
    out["high"], out["low"] = hi, lo
    report = {"dropped_late_bars": int((df.index.strftime("%H:%M") >= SESSION_END).sum()),
              "dropped_sessions": [d.date() for d in dropped_days], "repaired_ohlc": repaired}
    return out, report
