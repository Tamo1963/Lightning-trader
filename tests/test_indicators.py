import numpy as np
import pandas as pd

from lightning.indicators import atr, rsi, session_vwap, supertrend, vwma


def test_rsi_bounds_and_trend():
    up = pd.Series(np.arange(1.0, 60.0))
    assert rsi(up).dropna().iloc[-1] == 100
    down = pd.Series(np.arange(60.0, 1.0, -1))
    assert rsi(down).dropna().iloc[-1] == 0
    flat = pd.Series([5.0] * 40)
    assert rsi(flat).dropna().iloc[-1] == 50
    r = rsi(pd.Series(np.random.default_rng(0).normal(0, 1, 300).cumsum() + 100)).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_rsi_matches_plain_python_wilder():
    c = [44, 44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.0, 45.5]
    d = [y - x for x, y in zip(c, c[1:])]
    g, l = [max(x, 0) for x in d], [max(-x, 0) for x in d]
    ag, al = sum(g[:14]) / 14, sum(l[:14]) / 14
    expected = [100 - 100 / (1 + ag / al)]
    for k in range(14, len(d)):
        ag, al = (ag * 13 + g[k]) / 14, (al * 13 + l[k]) / 14
        expected.append(100 - 100 / (1 + ag / al))
    got = rsi(pd.Series(c), 14).dropna().tolist()
    assert np.allclose(got, expected)


def test_supertrend_flips_on_reversal():
    n = 80
    c = pd.Series(np.concatenate([np.linspace(100, 140, 40), np.linspace(140, 90, 40)]))
    h, l = c + 0.5, c - 0.5
    _, d = supertrend(h, l, c, 10, 3.0)
    assert d.iloc[35] == 1 and d.iloc[-1] == -1


def test_vwap_resets_each_session(synth):
    fut, _ = synth
    v = session_vwap(fut.iloc[:60])
    first_bar = fut.index[0]
    tp = (fut["high"].iat[0] + fut["low"].iat[0] + fut["close"].iat[0]) / 3
    assert abs(v.iloc[0] - tp) < 1e-9
    nxt = fut.index.normalize().unique()[1]
    i = list(fut.index.normalize()).index(nxt)
    tp2 = (fut["high"].iat[i] + fut["low"].iat[i] + fut["close"].iat[i]) / 3
    assert abs(session_vwap(fut.iloc[:60]).iloc[i] - tp2) < 1e-9


def test_vwma_weights_by_volume():
    c = pd.Series([10.0, 20.0]); v = pd.Series([1.0, 3.0])
    assert abs(vwma(c, v, 2).iloc[1] - 17.5) < 1e-12
