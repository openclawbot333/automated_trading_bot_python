import pandas as pd
import numpy as np
import yfinance as yf
from ta.trend import ADXIndicator
from datetime import datetime

SYMBOL = "ES=F"
START = "2026-01-29"
END = "2026-02-13"  # inclusive end for yf

# Fetch 5m data
m5 = yf.download(SYMBOL, start=START, end=END, interval="5m", auto_adjust=False, progress=False)
if m5.empty:
    raise SystemExit("No data fetched.")

# Flatten MultiIndex columns if present
if isinstance(m5.columns, pd.MultiIndex):
    m5.columns = m5.columns.get_level_values(0)

# yfinance index may already be tz-aware
if m5.index.tz is None:
    m5 = m5.tz_localize("UTC")

m5 = m5.tz_convert("America/New_York")
m5 = m5.dropna()

# Build H1 bars
h1 = m5.resample("1h").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()

# H1 swings: 2-2 fractal
h1["swing_high"] = (h1["High"] > h1["High"].shift(1)) & (h1["High"] > h1["High"].shift(2)) & (h1["High"] > h1["High"].shift(-1)) & (h1["High"] > h1["High"].shift(-2))
h1["swing_low"] = (h1["Low"] < h1["Low"].shift(1)) & (h1["Low"] < h1["Low"].shift(2)) & (h1["Low"] < h1["Low"].shift(-1)) & (h1["Low"] < h1["Low"].shift(-2))

# ADX on H1
adx = ADXIndicator(h1["High"], h1["Low"], h1["Close"], window=14)
h1["adx"] = adx.adx()

# Helper: latest fresh swing level (allow one touch)
fresh_high = None
fresh_low = None
fresh_high_time = None
fresh_low_time = None
high_touches = 0
low_touches = 0

trades = []

# Precompute M5 swings for BOS
m5["m5_swing_high"] = (m5["High"] > m5["High"].shift(1)) & (m5["High"] > m5["High"].shift(2)) & (m5["High"] > m5["High"].shift(-1)) & (m5["High"] > m5["High"].shift(-2))
m5["m5_swing_low"] = (m5["Low"] < m5["Low"].shift(1)) & (m5["Low"] < m5["Low"].shift(2)) & (m5["Low"] < m5["Low"].shift(-1)) & (m5["Low"] < m5["Low"].shift(-2))

# Track daily attempts
attempts = {}

h1_index = h1.index
for i in range(2, len(h1_index)-2):
    t = h1_index[i]
    row = h1.loc[t]

    # update fresh levels
    if row["swing_high"]:
        fresh_high = row["High"]
        fresh_high_time = t
        high_touches = 0
    if row["swing_low"]:
        fresh_low = row["Low"]
        fresh_low_time = t
        low_touches = 0

    # Allow one touch; invalidate after 2+ touches or full trade-through
    if fresh_high is not None:
        if row["High"] >= fresh_high:
            high_touches += 1
        if high_touches >= 2 or row["High"] > fresh_high:
            fresh_high = None
            fresh_high_time = None
            high_touches = 0
    if fresh_low is not None:
        if row["Low"] <= fresh_low:
            low_touches += 1
        if low_touches >= 2 or row["Low"] < fresh_low:
            fresh_low = None
            fresh_low_time = None
            low_touches = 0

    # Sweep check: allow confirmation on same or next H1 candle close
    sweep = None
    sweep_level = None

    # same candle confirmation
    if fresh_high is not None and row["High"] > fresh_high and row["Close"] < fresh_high:
        sweep = "short"
        sweep_level = fresh_high
    if fresh_low is not None and row["Low"] < fresh_low and row["Close"] > fresh_low:
        sweep = "long"
        sweep_level = fresh_low

    # next candle confirmation (look back one candle)
    if sweep is None and i > 0:
        prev = h1.iloc[i-1]
        if fresh_high is not None and prev["High"] > fresh_high and row["Close"] < fresh_high:
            sweep = "short"
            sweep_level = fresh_high
        if fresh_low is not None and prev["Low"] < fresh_low and row["Close"] > fresh_low:
            sweep = "long"
            sweep_level = fresh_low

    if sweep is None:
        continue

    day = t.date()
    attempts.setdefault(day, 0)
    if attempts[day] >= 2:
        continue

    # Look for M5 BOS + OB retest within next 12 M5 candles
    m5_window = m5[(m5.index > t) & (m5.index <= t + pd.Timedelta(hours=1))]
    if m5_window.empty:
        continue

    # Determine BOS
    entry = None
    stop = None
    target = None
    entry_time = None

    for j in range(2, len(m5_window)-2):
        tt = m5_window.index[j]
        r = m5_window.loc[tt]

        # Most recent swing level prior to tt
        prev_swings = m5_window.loc[:tt]
        last_swing_high = prev_swings[prev_swings["m5_swing_high"]]["High"].tail(1)
        last_swing_low = prev_swings[prev_swings["m5_swing_low"]]["Low"].tail(1)
        if sweep == "short":
            if last_swing_low.empty:
                continue
            bos_level = last_swing_low.iloc[-1]
            if r["Low"] < bos_level:
                # Order block = last bullish candle before BOS
                ob = prev_swings[prev_swings["Close"] > prev_swings["Open"]].tail(1)
                if ob.empty:
                    continue
                ob_high = ob["High"].iloc[-1]
                # retest within next 12 candles
                future = m5_window.loc[tt:tt + pd.Timedelta(minutes=60)].head(12)
                retest = future[future["High"] >= ob_high]
                if retest.empty:
                    continue
                entry_time = retest.index[0]
                entry = ob_high
                # breaker = last swing high before BOS
                last_sw_high = last_swing_high.iloc[-1] if not last_swing_high.empty else ob_high
                adx_val = h1.loc[t]["adx"]
                if adx_val < 20:
                    stop = h1.loc[t]["High"]  # conservative
                else:
                    stop = last_sw_high  # aggressive
                risk = stop - entry
                target = entry - 2 * risk
                break
        else:  # long
            if last_swing_high.empty:
                continue
            bos_level = last_swing_high.iloc[-1]
            if r["High"] > bos_level:
                ob = prev_swings[prev_swings["Close"] < prev_swings["Open"]].tail(1)
                if ob.empty:
                    continue
                ob_low = ob["Low"].iloc[-1]
                future = m5_window.loc[tt:tt + pd.Timedelta(minutes=60)].head(12)
                retest = future[future["Low"] <= ob_low]
                if retest.empty:
                    continue
                entry_time = retest.index[0]
                entry = ob_low
                last_sw_low = last_swing_low.iloc[-1] if not last_swing_low.empty else ob_low
                adx_val = h1.loc[t]["adx"]
                if adx_val < 20:
                    stop = h1.loc[t]["Low"]
                else:
                    stop = last_sw_low
                risk = entry - stop
                target = entry + 2 * risk
                break

    if entry is None:
        continue

    # Simulate trade on M5 from entry_time
    data_after = m5[m5.index >= entry_time]
    exit_time = None
    exit_price = None
    outcome = None

    # time exits: risk off at 11:00
    for tt, rr in data_after.iterrows():
        if sweep == "short":
            if rr["High"] >= stop:
                exit_time = tt
                exit_price = stop
                outcome = "stop"
                break
            if rr["Low"] <= target:
                exit_time = tt
                exit_price = target
                outcome = "target"
                break
        else:
            if rr["Low"] <= stop:
                exit_time = tt
                exit_price = stop
                outcome = "stop"
                break
            if rr["High"] >= target:
                exit_time = tt
                exit_price = target
                outcome = "target"
                break
        # risk off at 11:00: move stop to BE
        if tt.time() >= pd.Timestamp("11:00").time() and outcome is None:
            stop = entry

    if exit_time is None:
        continue

    attempts[day] += 1
    pnl = (entry - exit_price) if sweep == "short" else (exit_price - entry)
    trades.append({
        "day": day,
        "direction": sweep,
        "entry_time": entry_time,
        "entry": entry,
        "stop": stop,
        "target": target,
        "exit_time": exit_time,
        "exit": exit_price,
        "outcome": outcome,
        "pnl": pnl,
    })

# Results
trades_df = pd.DataFrame(trades)
trades_df.to_csv("backtest_jadecap_daily_sweep_trades.csv", index=False)

if len(trades_df) == 0:
    summary = {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0,
        "total_pnl": 0,
        "avg_pnl": 0,
        "note": "No trades matched rules in this date range",
    }
else:
    summary = {
        "trades": len(trades_df),
        "wins": int((trades_df["pnl"] > 0).sum()),
        "losses": int((trades_df["pnl"] <= 0).sum()),
        "win_rate": float((trades_df["pnl"] > 0).mean()),
        "total_pnl": float(trades_df["pnl"].sum()),
        "avg_pnl": float(trades_df["pnl"].mean()),
    }

pd.Series(summary).to_csv("backtest_jadecap_daily_sweep_summary.csv")
print(summary)
