# jadecap daily sweep

## Overview
Daily Sweep Protocol: (1) plot fresh H1 swing points at 8:00 AM, (2) require H1 candle **body close** back in range after a sweep, (3) execute on M5 with retest entry, partials at +10 MES points, final at 2R, and **risk off at 11:00 AM**.

## Phase I — Reconnaissance (08:00 AM ET)
- Work **only on the H1 chart**.
- Identify **previous day’s H1 swing points**.
- Plot **only untraded/fresh levels** (untouched liquidity).
- If the previous day is fully traded, **revert to the next most recent day** for fresh levels.

## Phase II — The Filter (Hourly Closure Rule)
- A sweep alone is **not** a trade.
- Valid when price **touches/raids** the level and the **H1 candle body closes back inside the range** (same candle or next candle).
- A sweep without closure = **volatility** → **no entry**.
- **Ignore 1m/5m/15m** until H1 confirms.

## Phase III — Engagement (M5 Trigger) — Relaxed
- After H1 confirmation, drop to **M5**.
- **Entry model (bearish example; invert for bullish):**
  1) Sweep (liquidity raid)
  2) **Market structure shift (BOS)**
  3) **Enter on retest of the BOS level** (breaker/OB alignment optional)

## Risk Protocol
- **Instrument:** MES (Micro E-mini S&P)
- **Position size:** 10 contracts
- **Standard stop:** above the structure that confirmed the entry (above BOS retest level for shorts; below for longs).
- **Chop / PM session (1:00–4:00 PM):** use **H1 high/low stop** (wider stop).
- **Targets:**
  - Take **partial (5 contracts)** at **+10 MES points**
  - Take **remaining (5 contracts)** at **final 2R target**
- **Two‑bullet rule:** max **2 attempts/day** (if AM fails, allow exactly one more attempt).

## Exit Protocols
- **Risk off at 11:00 AM** (take partials or move stop to breakeven).
- Do not carry full risk into low‑volume lunch window.

## Checklist
- [08:00 AM] Plot untraded H1 swing points
- [Filter] Wait for H1 candle **body close** (rejection)
- [Execution] M5 breaker + order‑block alignment
- [Contingency] PM/chop → H1 stop
- [Exit] Risk off at 11:00 AM

## Notes
- Simplicity > complexity. Steps 1–2 are rigid rules; execution requires reps.
