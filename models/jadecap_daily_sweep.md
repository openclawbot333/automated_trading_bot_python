# jadecap daily sweep

## Overview
Daily Sweep is a three‑step strategy: mark prior swing points, wait for hourly confirmation, then execute on the 5‑minute chart with defined risk and time‑based exits.

## Step 1 — Plot Swing Points (8:00–8:30 AM ET)
- Mark **hourly swing points** from the previous day and the hours leading up to 8:00 AM (London/Asia sessions).
- **Only mark swing points not yet traded through.**
- If price is trading beyond the previous day’s swing highs, use the **next most recent high from the day before**.
- Expected time: **5–10 minutes** across markets.

## Step 2 — Confirmation Filter (Hourly Close Rule)
- **Do not enter on a raid alone.**
- Wait for the **hourly candle to close back inside the range** after sweeping a swing high/low.
- **No lower‑timeframe execution** until the hourly candle closes.

## Step 3 — 5‑Minute Execution
- After hourly confirmation, drop to **5‑minute** chart.
- **Entry model:**
  - Bearish order block (series of up‑close candles) followed by a **break below the low**, or
  - A **breaker** structure aligning with the sweep rejection.
- **Stop‑loss:**
  - Default: above the breaker or logical high.
  - If choppy/sideways: **use higher‑timeframe stop** (e.g., above hourly high) for wiggle room.
- **Target:** **2R** (2:1 reward‑to‑risk).
- **Time exits:** consider partials or moving stops into the **11:00 AM–12:00 PM** lunch window.

## Risk & Limits
- **Max attempts per day:** 2 (if initial attempt loses, limit to two total attempts).
- **Risk:** consistent position sizing (default 1 contract per overall model).

## Example Scenarios
- **Perfect setup:** 9:00 AM hourly candle raids a swing high and closes back in range → 10:00 AM 5‑min bearish order block + breaker → short to 2R.
- **Choppy morning:** first trade loses → limit to two attempts; in PM session (1:00–4:00 PM), widen stop above hourly high.

## Notes
- Consistency and repetition are emphasized; adjust stop‑loss placement based on market structure (tight FVG stops vs higher‑timeframe stops).
