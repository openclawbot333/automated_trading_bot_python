"""
Backtest: Bearish on a Gap Up — NQ Model

Fetches NQ and ES data via yfinance, applies the model rules,
simulates trades with 3-tier exits, and outputs results.
"""

import sys
import os
import yaml
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.models.bearish_on_gap_up import BearishOnGapUpModel

# ------------------------------------------------------------------ #
#  Load Config
# ------------------------------------------------------------------ #
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "bearish_on_gap_up.yaml")
with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

model = BearishOnGapUpModel(config)

NQ_SYMBOL = config.get("yfinance_symbol", "NQ=F")
ES_SYMBOL = config.get("es_symbol", "ES=F")

# ------------------------------------------------------------------ #
#  Fetch Data
# ------------------------------------------------------------------ #
print(f"Fetching daily data for {NQ_SYMBOL} and {ES_SYMBOL}...")

# Daily data — longer lookback for context
nq_daily = yf.download(NQ_SYMBOL, period="60d", interval="1d", auto_adjust=False, progress=False)
es_daily = yf.download(ES_SYMBOL, period="60d", interval="1d", auto_adjust=False, progress=False)

# Flatten MultiIndex columns if present
for df in [nq_daily, es_daily]:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

if nq_daily.empty or es_daily.empty:
    raise SystemExit("Failed to fetch daily data.")

# Ensure timezone
for df in [nq_daily, es_daily]:
    if df.index.tz is None:
        df.index = df.index.tz_localize("America/New_York")
    else:
        df.index = df.index.tz_convert("America/New_York")

print(f"  NQ daily: {len(nq_daily)} bars ({nq_daily.index[0].date()} to {nq_daily.index[-1].date()})")
print(f"  ES daily: {len(es_daily)} bars")

# Intraday data — 5-min as proxy for 1-min (yfinance limitation)
# yfinance allows up to 60 days of 5-min data
print(f"Fetching 5-min intraday data for {NQ_SYMBOL}...")
nq_m5 = yf.download(NQ_SYMBOL, period="60d", interval="5m", auto_adjust=False, progress=False)

if isinstance(nq_m5.columns, pd.MultiIndex):
    nq_m5.columns = nq_m5.columns.get_level_values(0)

if nq_m5.empty:
    raise SystemExit("Failed to fetch intraday data.")

if nq_m5.index.tz is None:
    nq_m5 = nq_m5.tz_localize("UTC")
nq_m5 = nq_m5.tz_convert("America/New_York")
nq_m5 = nq_m5.dropna()

print(f"  NQ 5-min: {len(nq_m5)} bars")

# ------------------------------------------------------------------ #
#  Daily Analysis
# ------------------------------------------------------------------ #
print("\n--- Daily Analysis ---")

sb = model.identify_suspension_block(nq_daily)
print(f"Suspension Block: High={sb['high']:.2f}, Low={sb['low']:.2f}, CE={sb['ce']:.2f}, Valid={sb['valid']}")

bearish = model.check_daily_bias(nq_daily, sb)
print(f"Daily Bias Bearish: {bearish}")

smt = model.check_smt_divergence(nq_daily, es_daily, config.get("smt_lookback", 20))
print(f"SMT Divergence: {smt}")

spring_ok = model.check_spring_filter(nq_daily)
print(f"Spring Filter (ok to trade): {spring_ok}")

wicks = model.grade_wicks(nq_daily)
print(f"Significant Wicks: {len(wicks)}")

nwog = model.calculate_nwog(nq_daily)
print(f"NWOG: {nwog:.2f}" if nwog else "NWOG: None")

# ------------------------------------------------------------------ #
#  Backtest: Walk through trading days
# ------------------------------------------------------------------ #
print("\n--- Backtesting ---")

session_start = config.get("session_start", "08:00")
session_end = config.get("session_end", "16:00")
tp1_pct = config.get("tp1_pct", 0.50)
tp2_pct = config.get("tp2_pct", 0.30)
tp3_pct = config.get("tp3_pct", 0.20)

trades = []
daily_pnl = {}
trading_days = sorted(nq_m5.index.date)
trading_days = sorted(set(trading_days))

for day in trading_days:
    day_str = str(day)

    # Check daily max loss
    if day in daily_pnl and daily_pnl[day] <= -(config["account_equity"] * config["max_daily_loss_pct"]):
        continue

    # Get daily data up to this day for context
    daily_mask = nq_daily.index.date <= day
    nq_d = nq_daily[daily_mask]
    es_d = es_daily[es_daily.index.date <= day]

    if len(nq_d) < 10 or len(es_d) < 10:
        continue

    # Daily checks
    sb = model.identify_suspension_block(nq_d)
    if not sb["valid"]:
        continue

    if not model.check_daily_bias(nq_d, sb):
        continue

    smt_ok = model.check_smt_divergence(nq_d, es_d)
    spring = model.check_spring_filter(nq_d)
    if not spring:
        continue

    # Get intraday data for this session
    day_m5 = nq_m5[nq_m5.index.date == day]
    if day_m5.empty:
        continue

    # Filter to NY session
    session_mask = (day_m5.index.time >= pd.Timestamp(session_start).time()) & \
                   (day_m5.index.time <= pd.Timestamp(session_end).time())
    session_data = day_m5[session_mask]
    if len(session_data) < 10:
        continue

    # Detect FVGs
    fvgs = model.detect_fvg(session_data)

    # Find entry
    entry = model.find_entry(session_data, sb, fvgs)
    if entry is None:
        continue

    # Calculate stop and targets
    stop = model.calculate_stop(sb)
    nwog_val = model.calculate_nwog(nq_d)
    ssl = model.find_sellside_liquidity(session_data)

    gradient_levels = []
    for w in model.grade_wicks(nq_d):
        gradient_levels.extend(w["levels"].values())

    targets = model.calculate_targets(entry["price"], nwog_val, ssl, gradient_levels)

    size = model._calculate_position_size(entry["price"], stop)

    # Risk check
    risk_points = stop - entry["price"]
    risk_dollars = risk_points * size * model.micro_value
    if risk_dollars > config["account_equity"] * config["max_risk_pct"]:
        continue

    # ---- Simulate trade ---- #
    entry_price = entry["price"]
    entry_time = entry["time"]
    tp1 = targets["tp1"]
    tp2 = targets["tp2"]
    tp3 = targets["tp3"]

    # Track remaining position fractions
    remaining = 1.0
    realized_pnl = 0.0
    exit_time = None
    exit_reason = None
    be_stop = False  # breakeven stop after TP1

    after_entry = session_data[session_data.index >= entry_time]

    for idx, bar in after_entry.iterrows():
        current_stop = entry_price if be_stop else stop

        # Check stop hit
        if bar["High"] >= current_stop and remaining > 0:
            pnl_pts = entry_price - current_stop  # short: entry - exit
            realized_pnl += pnl_pts * remaining
            exit_time = idx
            exit_reason = "stop" if not be_stop else "breakeven"
            remaining = 0
            break

        # Check TP1
        if remaining > (1 - tp1_pct + 0.01) and bar["Low"] <= tp1:
            pnl_pts = entry_price - tp1
            realized_pnl += pnl_pts * tp1_pct
            remaining -= tp1_pct
            be_stop = True  # Move stop to breakeven

        # Check TP2
        if remaining > tp3_pct + 0.01 and bar["Low"] <= tp2:
            pnl_pts = entry_price - tp2
            realized_pnl += pnl_pts * tp2_pct
            remaining -= tp2_pct

        # Check TP3
        if remaining > 0.01 and bar["Low"] <= tp3:
            pnl_pts = entry_price - tp3
            realized_pnl += pnl_pts * remaining
            exit_time = idx
            exit_reason = "tp3"
            remaining = 0
            break

    # If position still open at session end, close at last price
    if remaining > 0.01:
        last_price = after_entry["Close"].iloc[-1] if len(after_entry) > 0 else entry_price
        pnl_pts = entry_price - last_price
        realized_pnl += pnl_pts * remaining
        exit_time = after_entry.index[-1] if len(after_entry) > 0 else entry_time
        exit_reason = "session_end"

    pnl_dollars = realized_pnl * size * model.micro_value
    daily_pnl.setdefault(day, 0)
    daily_pnl[day] += pnl_dollars

    trades.append({
        "day": day,
        "entry_time": entry_time,
        "entry_type": entry["type"],
        "entry_price": entry_price,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "size": size,
        "smt": smt_ok,
        "exit_time": exit_time,
        "exit_reason": exit_reason,
        "pnl_points": round(realized_pnl, 2),
        "pnl_dollars": round(pnl_dollars, 2),
    })

# ------------------------------------------------------------------ #
#  Output Results
# ------------------------------------------------------------------ #
trades_df = pd.DataFrame(trades)
output_dir = os.path.join(os.path.dirname(__file__), "..")
trades_csv = os.path.join(output_dir, "backtest_bearish_gap_up_trades.csv")
summary_csv = os.path.join(output_dir, "backtest_bearish_gap_up_summary.csv")

trades_df.to_csv(trades_csv, index=False)

if len(trades_df) == 0:
    summary = {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0,
        "total_pnl_pts": 0,
        "total_pnl_dollars": 0,
        "avg_pnl_pts": 0,
        "avg_pnl_dollars": 0,
        "note": "No trades matched rules in this period. This is normal — the model is selective.",
    }
else:
    summary = {
        "trades": len(trades_df),
        "wins": int((trades_df["pnl_points"] > 0).sum()),
        "losses": int((trades_df["pnl_points"] <= 0).sum()),
        "win_rate": round(float((trades_df["pnl_points"] > 0).mean()), 4),
        "total_pnl_pts": round(float(trades_df["pnl_points"].sum()), 2),
        "total_pnl_dollars": round(float(trades_df["pnl_dollars"].sum()), 2),
        "avg_pnl_pts": round(float(trades_df["pnl_points"].mean()), 2),
        "avg_pnl_dollars": round(float(trades_df["pnl_dollars"].mean()), 2),
        "max_win_pts": round(float(trades_df["pnl_points"].max()), 2),
        "max_loss_pts": round(float(trades_df["pnl_points"].min()), 2),
        "smt_confirmed_pct": round(float(trades_df["smt"].mean()), 4),
    }

pd.Series(summary).to_csv(summary_csv)

print("\n=== BACKTEST RESULTS ===")
for k, v in summary.items():
    print(f"  {k}: {v}")
print(f"\nTrades saved to: {trades_csv}")
print(f"Summary saved to: {summary_csv}")
