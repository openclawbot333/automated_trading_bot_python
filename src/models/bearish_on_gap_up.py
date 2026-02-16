"""Bearish on a Gap Up model implementation.

Core philosophy: sell short into rallies within a bearish daily framework.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from ta.trend import ADXIndicator


class BearishOnGapUpModel:
    """Core logic for the Bearish on a Gap Up model."""

    def __init__(self, config: dict):
        self.config = config or {}
        self.stop_buffer = float(self.config.get("stop_buffer_points", 7.5))
        self.adx_threshold = float(self.config.get("spring_filter_adx_threshold", 20))
        self.smt_lookback = int(self.config.get("smt_lookback", 20))
        self.wick_ratio = float(self.config.get("wick_significance_ratio", 0.5))
        self.equal_lows_tol = float(self.config.get("equal_lows_tolerance", 2.0))

    # ------------------------------------------------------------------ #
    #  Daily Suspension Block & Bias
    # ------------------------------------------------------------------ #

    def identify_suspension_block(self, daily_data: pd.DataFrame) -> Dict[str, float | bool]:
        """Find swing high and volume bounce low to define the block.

        Returns: {'high': float, 'low': float, 'ce': float, 'valid': bool}
        """
        if daily_data is None or daily_data.empty or len(daily_data) < 10:
            return {"high": np.nan, "low": np.nan, "ce": np.nan, "valid": False}

        data = daily_data.dropna().copy()
        if data.empty:
            return {"high": np.nan, "low": np.nan, "ce": np.nan, "valid": False}

        low_idx = data["Low"].idxmin()
        low = float(data.loc[low_idx, "Low"])
        post_low = data.loc[low_idx:]
        if post_low.empty:
            return {"high": np.nan, "low": low, "ce": np.nan, "valid": False}

        high = float(post_low["High"].max())
        valid = high > low
        ce = (high + low) / 2 if valid else np.nan
        return {"high": high, "low": low, "ce": ce, "valid": valid}

    def check_daily_bias(self, daily_data: pd.DataFrame, suspension_block: dict) -> bool:
        """True if latest close < CE and block is valid."""
        if not suspension_block.get("valid", False):
            return False
        if daily_data is None or daily_data.empty:
            return False
        latest_close = float(daily_data["Close"].iloc[-1])
        return latest_close < float(suspension_block["ce"])

    # ------------------------------------------------------------------ #
    #  Wick grading
    # ------------------------------------------------------------------ #

    def grade_wicks(self, daily_data: pd.DataFrame) -> List[dict]:
        """Fibonacci gradient levels on significant lower wicks."""
        results: List[dict] = []
        if daily_data is None or daily_data.empty:
            return results

        fibs = list(self.config.get("fib_eighths", [])) + list(self.config.get("fib_quadrants", []))
        fibs = sorted(set(fibs))

        for idx, row in daily_data.iterrows():
            high = float(row["High"])
            low = float(row["Low"])
            open_ = float(row["Open"])
            close = float(row["Close"])
            total_range = high - low
            if total_range <= 0:
                continue

            wick_top = min(open_, close)
            lower_wick = wick_top - low
            if lower_wick / total_range < self.wick_ratio:
                continue

            levels = {f"{fib:.3f}": low + lower_wick * fib for fib in fibs}
            results.append({"date": idx, "wick_low": low, "wick_high": wick_top, "levels": levels})
        return results

    # ------------------------------------------------------------------ #
    #  SMT Divergence
    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_swing_highs(df: pd.DataFrame) -> List[float]:
        """Find simple swing highs with 2-bar left/right confirmation."""
        highs = []
        if df is None or len(df) < 5:
            return highs

        for i in range(2, len(df) - 2):
            h = df["High"].iloc[i]
            if h > df["High"].iloc[i - 1] and h > df["High"].iloc[i - 2] and h > df["High"].iloc[i + 1] and h > df["High"].iloc[i + 2]:
                highs.append(float(h))
        return highs

    def check_smt_divergence(self, nq_data: pd.DataFrame, es_data: pd.DataFrame, lookback: int = 20) -> bool:
        """NQ higher high + ES lower high = bearish SMT divergence."""
        if nq_data is None or es_data is None:
            return False

        nq = nq_data.iloc[-lookback:].copy() if len(nq_data) >= lookback else nq_data
        es = es_data.iloc[-lookback:].copy() if len(es_data) >= lookback else es_data

        nq_highs = self._find_swing_highs(nq)
        es_highs = self._find_swing_highs(es)
        if len(nq_highs) < 2 or len(es_highs) < 2:
            return False

        return (nq_highs[-1] > nq_highs[-2]) and (es_highs[-1] < es_highs[-2])

    # ------------------------------------------------------------------ #
    #  Fair Value Gaps
    # ------------------------------------------------------------------ #

    def detect_fvg(self, m1_data: pd.DataFrame) -> List[dict]:
        """Bearish FVGs: candle1_low > candle3_high."""
        fvgs: List[dict] = []
        if m1_data is None or len(m1_data) < 3:
            return fvgs

        for i in range(2, len(m1_data)):
            candle1 = m1_data.iloc[i - 2]
            candle3 = m1_data.iloc[i]
            if float(candle1["Low"]) > float(candle3["High"]):
                fvgs.append(
                    {
                        "index": m1_data.index[i],
                        "top": float(candle1["Low"]),
                        "bottom": float(candle3["High"]),
                    }
                )
        return fvgs

    def find_entry(self, m1_data: pd.DataFrame, suspension_block: dict, fvgs: List[dict]) -> Optional[dict]:
        """Entry when price rallies into FVG/CE and rejects."""
        if m1_data is None or m1_data.empty:
            return None

        last = m1_data.iloc[-1]
        last_high = float(last["High"])
        last_close = float(last["Close"])

        ce = float(suspension_block.get("ce", np.nan))
        if np.isfinite(ce) and last_high >= ce and last_close < ce:
            return {"price": last_close, "type": "ce"}

        for fvg in fvgs:
            if last_high >= fvg["bottom"] and last_close < fvg["bottom"]:
                return {"price": last_close, "type": "fvg"}

        return None

    # ------------------------------------------------------------------ #
    #  Risk / Targets
    # ------------------------------------------------------------------ #

    def calculate_stop(self, suspension_block: dict) -> float:
        """Hard stop above suspension block high + buffer."""
        return float(suspension_block["high"]) + self.stop_buffer

    def calculate_targets(
        self, entry_price: float, nwog: Optional[float], sellside_levels: List[float], gradient_levels: List[float]
    ) -> dict:
        """3-tier targets (scalar levels)."""
        tp1 = nwog if nwog is not None and nwog < entry_price else None
        tp2 = max([lvl for lvl in sellside_levels if lvl < entry_price], default=None)
        tp3 = max([lvl for lvl in gradient_levels if lvl < entry_price], default=None)
        return {"tp1": tp1, "tp2": tp2, "tp3": tp3}

    def calculate_nwog(self, daily_data: pd.DataFrame) -> Optional[float]:
        """Friday close vs Monday open gap reference."""
        if daily_data is None or len(daily_data) < 3:
            return None
        data = daily_data.sort_index()
        for i in range(1, len(data)):
            prev_date = data.index[i - 1]
            date = data.index[i]
            if prev_date.weekday() == 4 and date.weekday() == 0:
                return float(data.iloc[i]["Open"])
        return None

    def find_sellside_liquidity(self, m1_data: pd.DataFrame, lookback: int = 100) -> List[float]:
        """Clusters of equal lows within tolerance."""
        if m1_data is None or m1_data.empty:
            return []

        lows = m1_data["Low"].iloc[-lookback:].values
        lows = np.sort(lows)
        clusters: List[List[float]] = []

        for low in lows:
            placed = False
            for cluster in clusters:
                if abs(low - np.mean(cluster)) <= self.equal_lows_tol:
                    cluster.append(float(low))
                    placed = True
                    break
            if not placed:
                clusters.append([float(low)])

        return [float(np.mean(c)) for c in clusters if len(c) >= 2]

    # ------------------------------------------------------------------ #
    #  Spring Filter
    # ------------------------------------------------------------------ #

    def check_spring_filter(self, daily_data: pd.DataFrame) -> bool:
        """ADX-based choppy market filter.

        If insufficient data (< 14 bars), allow trading.
        """
        if daily_data is None or len(daily_data) < 14:
            return True

        try:
            adx = ADXIndicator(
                high=daily_data["High"],
                low=daily_data["Low"],
                close=daily_data["Close"],
                window=14,
            ).adx()
            latest = float(adx.iloc[-1])
            return bool(latest >= self.adx_threshold)
        except Exception:
            # If ADX calculation fails, default to allowing trades.
            return True

    # ------------------------------------------------------------------ #
    #  Checklist & Signal
    # ------------------------------------------------------------------ #

    def evaluate_checklist(
        self,
        suspension_block: dict,
        daily_bias_bearish: bool,
        smt_confirmed: bool,
        entry: Optional[dict],
        position_size: int,
        stop: float,
        targets_identified: bool,
        spring_filter_pass: bool,
    ) -> dict:
        """Evaluate pre-trade checklist flags (used in tests)."""
        return {
            "suspension_block_valid": suspension_block.get("valid", False),
            "daily_bias_bearish": bool(daily_bias_bearish),
            "smt_divergence": bool(smt_confirmed),
            "entry_at_fvg_or_ce": entry is not None,
            "position_size_valid": position_size >= 1,
            "stop_defined": stop is not None,
            "targets_identified": bool(targets_identified),
            "spring_filter_pass": bool(spring_filter_pass),
        }

    def generate_signal(self, nq_daily: pd.DataFrame, es_daily: pd.DataFrame, nq_m1: pd.DataFrame) -> Optional[dict]:
        """Orchestrator method for signal generation."""
        suspension_block = self.identify_suspension_block(nq_daily)
        if not suspension_block.get("valid", False):
            return None

        daily_bias = self.check_daily_bias(nq_daily, suspension_block)
        smt = self.check_smt_divergence(nq_daily, es_daily, lookback=self.smt_lookback)
        fvgs = self.detect_fvg(nq_m1)
        entry = self.find_entry(nq_m1, suspension_block, fvgs)
        spring_pass = self.check_spring_filter(nq_daily)

        if not all([daily_bias, smt, spring_pass, entry]):
            return None

        nwog = self.calculate_nwog(nq_daily)
        sellside = self.find_sellside_liquidity(nq_m1)
        gradients = []
        for wick in self.grade_wicks(nq_daily):
            gradients.extend(list(wick["levels"].values()))

        targets = self.calculate_targets(entry["price"], nwog, sellside, gradients)
        stop = self.calculate_stop(suspension_block)

        checklist = self.evaluate_checklist(
            suspension_block, daily_bias, smt, entry, 1, stop, targets["tp1"] is not None, spring_pass
        )

        return {
            "direction": "short",
            "entry": entry,
            "stop": stop,
            "targets": targets,
            "checklist": checklist,
        }
