"""Expiry and lot-size calendars. Weekly expiry weekday changed over time; a holiday moves expiry to the
previous trading day. Trading days come from the data itself, so historical holidays are handled."""
from __future__ import annotations

from bisect import bisect_left
from datetime import date, timedelta


def _in_effect(schedule: list[dict], d: date, key: str):
    val = None
    for row in schedule:  # sorted by "from"
        if d >= row["from"]:
            val = row[key]
    if val is None:
        raise ValueError(f"no schedule entry for {d}")
    return val


def lot_size_on(schedule: list[dict], d: date) -> int:
    return int(_in_effect(schedule, d, "lot"))


class ExpiryCalendar:
    def __init__(self, trading_days, schedule: list[dict]):
        days = sorted(set(trading_days))
        self._days = set(days)
        expiries, d, end = set(), days[0] - timedelta(days=days[0].weekday()), days[-1]
        while d <= end + timedelta(days=7):
            target = d + timedelta(days=_in_effect(schedule, max(d, schedule[0]["from"]), "weekday"))
            e = target
            while e not in self._days and e >= d and e <= end:
                e -= timedelta(days=1)
            if e in self._days:
                expiries.add(e)
            elif target > end:  # beyond the data: keep the nominal date
                expiries.add(target)
            d += timedelta(days=7)
        self.expiries = sorted(expiries)
        self._eset = set(self.expiries)

    def is_expiry(self, d: date) -> bool:
        return d in self._eset

    def nth_from(self, d: date, n: int) -> date:
        """n=0: first expiry on/after d (the near contract); n=1: the one after."""
        k = bisect_left(self.expiries, d)
        return self.expiries[k + n]

    def choose(self, d: date, min_dte_days: int) -> tuple[int, date]:
        """(0 or 1, expiry): near contract unless it expires within min_dte_days, then the next one."""
        near = self.nth_from(d, 0)
        return (0, near) if (near - d).days >= min_dte_days else (1, self.nth_from(d, 1))
