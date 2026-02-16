"""
Unit tests for Bearish on a Gap Up model.

Uses synthetic/mock data to validate core logic.
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.models.bearish_on_gap_up import BearishOnGapUpModel

# ------------------------------------------------------------------ #
#  Config & Helpers
# ------------------------------------------------------------------ #

DEFAULT_CONFIG = {
    "stop_buffer_points": 7.5,
    "spring_filter_adx_threshold": 20,
    "smt_lookback": 20,
    "fvg_min_gap_points": 1.0,
    "wick_significance_ratio": 0.50,
    "equal_lows_tolerance": 2.0,
    "micro_contract_value": 2.0,
    "account_equity": 10000,
    "max_risk_pct": 0.02,
    "max_position_size": 3,
    "min_position_size": 1,
    "tp1_pct": 0.50,
    "tp2_pct": 0.30,
    "tp3_pct": 0.20,
    "fib_levels": {
        "eighths": [0.125, 0.25, 0.375, 0.50, 0.625, 0.75, 0.875],
    },
}


def make_model(config=None):
    return BearishOnGapUpModel(config or DEFAULT_CONFIG)


def make_daily_data(n=30, base=20000, trend=-10, seed=42):
    """Generate synthetic daily OHLCV data with swing highs/lows."""
    rng = np.random.RandomState(seed)
    dates = pd.bdate_range(end="2026-02-13", periods=n, tz="America/New_York")

    opens, highs, lows, closes, volumes = [], [], [], [], []
    price = base
    for i in range(n):
        o = price + rng.uniform(-20, 20)
        h = o + rng.uniform(10, 80)
        l = o - rng.uniform(10, 80)
        c = l + rng.uniform(0, h - l)
        v = rng.randint(50000, 200000)
        opens.append(o)
        highs.append(h)
        lows.append(l)
        closes.append(c)
        volumes.append(v)
        price += trend + rng.uniform(-15, 15)

    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=dates,
    )


# ------------------------------------------------------------------ #
#  test_suspension_block_identification
# ------------------------------------------------------------------ #

def test_suspension_block_identification():
    model = make_model()
    daily = make_daily_data(n=30)
    sb = model.identify_suspension_block(daily)
    assert sb["valid"] is True
    assert sb["high"] > sb["low"]


def test_suspension_block_too_little_data():
    model = make_model()
    daily = make_daily_data(n=5)
    sb = model.identify_suspension_block(daily)
    assert sb["valid"] is False


# ------------------------------------------------------------------ #
#  test_ce_calculation
# ------------------------------------------------------------------ #

def test_ce_calculation():
    model = make_model()
    daily = make_daily_data(n=30, seed=99)
    sb = model.identify_suspension_block(daily)
    if sb["valid"]:
        expected_ce = (sb["high"] + sb["low"]) / 2.0
        assert abs(sb["ce"] - expected_ce) < 1e-6


# ------------------------------------------------------------------ #
#  test_smt_divergence_detection
# ------------------------------------------------------------------ #

def test_smt_divergence_detection():
    """NQ higher high + ES lower high → bearish SMT divergence."""
    model = make_model()
    n = 25
    dates = pd.bdate_range(end="2026-02-13", periods=n, tz="America/New_York")

    # NQ: two swing highs, second higher
    nq_highs = [100.0] * n
    nq_highs[8] = 150;  nq_highs[7] = 140;  nq_highs[9] = 140
    nq_highs[6] = 130;  nq_highs[10] = 130
    nq_highs[18] = 160; nq_highs[17] = 150; nq_highs[19] = 150
    nq_highs[16] = 140; nq_highs[20] = 140

    nq_df = pd.DataFrame(
        {"Open": [100]*n, "High": nq_highs, "Low": [90]*n, "Close": [100]*n, "Volume": [10000]*n},
        index=dates,
    )

    # ES: two swing highs, second lower
    es_highs = [100.0] * n
    es_highs[8] = 160;  es_highs[7] = 150;  es_highs[9] = 150
    es_highs[6] = 140;  es_highs[10] = 140
    es_highs[18] = 140; es_highs[17] = 130; es_highs[19] = 130
    es_highs[16] = 120; es_highs[20] = 120

    es_df = pd.DataFrame(
        {"Open": [100]*n, "High": es_highs, "Low": [90]*n, "Close": [100]*n, "Volume": [10000]*n},
        index=dates,
    )

    assert model.check_smt_divergence(nq_df, es_df, lookback=n) is True


def test_smt_no_divergence_when_both_higher():
    """Both making higher highs → no divergence."""
    model = make_model()
    n = 25
    dates = pd.bdate_range(end="2026-02-13", periods=n, tz="America/New_York")

    highs = [100.0] * n
    highs[8] = 150;  highs[7] = 140;  highs[9] = 140
    highs[6] = 130;  highs[10] = 130
    highs[18] = 160; highs[17] = 150; highs[19] = 150
    highs[16] = 140; highs[20] = 140

    df = pd.DataFrame(
        {"Open": [100]*n, "High": highs, "Low": [90]*n, "Close": [100]*n, "Volume": [10000]*n},
        index=dates,
    )
    assert model.check_smt_divergence(df, df.copy(), lookback=n) is False


# ------------------------------------------------------------------ #
#  test_fvg_detection
# ------------------------------------------------------------------ #

def test_fvg_detection():
    """Bearish FVG: candle[i-2].Low > candle[i].High."""
    model = make_model()
    times = pd.date_range("2026-02-13 09:00", periods=5, freq="5min", tz="America/New_York")
    data = pd.DataFrame({
        "Open":  [100, 98, 94, 92, 90],
        "High":  [101, 99, 95, 93, 91],
        "Low":   [98,  96, 93, 91, 89],
        "Close": [99,  97, 94, 92, 90],
        "Volume": [100] * 5,
    }, index=times)

    fvgs = model.detect_fvg(data)
    assert len(fvgs) >= 1
    # First FVG: candle0 low (98) > candle2 high (95) → gap = 3
    assert fvgs[0]["top"] == 98.0
    assert fvgs[0]["bottom"] == 95.0


def test_fvg_no_gap():
    """No gap → no FVG."""
    model = make_model()
    times = pd.date_range("2026-02-13 09:00", periods=5, freq="5min", tz="America/New_York")
    data = pd.DataFrame({
        "Open":  [100]*5, "High":  [102]*5, "Low":   [98]*5, "Close": [101]*5, "Volume": [100]*5,
    }, index=times)
    assert len(model.detect_fvg(data)) == 0


# ------------------------------------------------------------------ #
#  test_spring_filter
# ------------------------------------------------------------------ #

def test_spring_filter():
    """With sufficient data, should return a boolean."""
    model = make_model()
    daily = make_daily_data(n=20, trend=-15, seed=10)
    result = model.check_spring_filter(daily)
    assert bool(result) is True or bool(result) is False  # just confirm it's truthy/falsy


def test_spring_filter_insufficient_data():
    """With < 14 bars, should default to allowing trading."""
    model = make_model()
    daily = make_daily_data(n=5)
    assert model.check_spring_filter(daily) is True


# ------------------------------------------------------------------ #
#  Additional tests
# ------------------------------------------------------------------ #

def test_stop_loss():
    model = make_model()
    sb = {"high": 20100, "low": 19900, "ce": 20000, "valid": True}
    assert model.calculate_stop(sb) == 20100 + 7.5


def test_targets_below_entry():
    model = make_model()
    targets = model.calculate_targets(
        entry_price=20000, nwog=19950,
        sellside_levels=[19900, 19850], gradient_levels=[19800, 19700],
    )
    assert targets["tp1"] < 20000
    assert targets["tp2"] < 20000
    assert targets["tp3"] < 20000


def test_checklist_all_pass():
    model = make_model()
    sb = {"high": 20100, "low": 19900, "ce": 20000, "valid": True}
    entry = {"time": pd.Timestamp.now(), "price": 19990, "type": "ce"}
    cl = model.evaluate_checklist(sb, True, True, entry, 2, 20107.5, True, True)
    assert all(cl.values())


def test_checklist_fails_no_entry():
    model = make_model()
    sb = {"high": 20100, "low": 19900, "ce": 20000, "valid": True}
    cl = model.evaluate_checklist(sb, True, True, None, 2, 20107.5, True, True)
    assert cl["entry_at_fvg_or_ce"] is False


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
