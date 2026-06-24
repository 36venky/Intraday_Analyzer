import os
import numpy as np
from sklearn.linear_model import LinearRegression

from Structure.Highs_Lows import (
    get_confirmed_swings,
    build_swing_zones,
    previous_day_levels,
)


# =========================================================
# SWING POINTS
# =========================================================
def swing_points(highs, lows, window=3):

    swing_highs = []
    swing_lows = []

    for i in range(window, len(highs) - window):

        if highs[i] == max(highs[i-window:i+window+1]):
            swing_highs.append(i)

        if lows[i] == min(lows[i-window:i+window+1]):
            swing_lows.append(i)

    return swing_lows, swing_highs


# =========================================================
# FILTER SWINGS
# =========================================================
def filter_swings(indices, values, min_move=0.005):

    if len(indices) == 0:
        return []

    filtered = [indices[0]]

    for idx in indices[1:]:

        prev = filtered[-1]

        move = abs(values[idx] - values[prev]) / values[prev]

        if move >= min_move:
            filtered.append(idx)

    return filtered


# =========================================================
# TOUCH COUNT
# =========================================================
def count_touches(series, start_idx, level, buffer_pct=0.001):

    touches = []

    for i in range(start_idx + 1, len(series)):

        diff = abs(series[i] - level) / level

        if diff <= buffer_pct:
            touches.append(i)

    return touches


# =========================================================
# DUPLICATE FILTER
# =========================================================
def is_far_from_existing(level, existing, tol=0.001):

    return all(abs(level - x) / x > tol for x in existing)


# =========================================================
# FIT LINE
# =========================================================
def fit_line(indices, values):

    X = np.array(indices).reshape(-1, 1)

    y = values[indices]

    model = LinearRegression().fit(X, y)

    y_pred = model.predict(X)

    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)

    r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

    return model.coef_[0], model.intercept_, r2


# =========================================================
# GOOD FIT
# =========================================================
def is_good_fit(indices,
                values,
                slope,
                intercept,
                tol=0.003):

    for i in indices:

        expected = slope * i + intercept

        diff = abs(values[i] - expected) / abs(expected)

        if diff > tol:
            return False

    return True


# =========================================================
# BUILD TRENDLINES
# =========================================================
def build_trendlines(indices,
                     values,
                     tol=0.004,
                     min_points=3,
                     r2_min=0.85):

    lines = []

    n = len(indices)

    i = 0

    while i < n - 1:

        current = [indices[i], indices[i+1]]

        j = i + 2

        while j < n:

            trial = current + [indices[j]]

            slope, intercept, r2 = fit_line(
                trial,
                values
            )

            if is_good_fit(
                trial,
                values,
                slope,
                intercept,
                tol
            ):
                current.append(indices[j])
                j += 1
            else:
                break

        if len(current) >= min_points:

            slope, intercept, r2 = fit_line(
                current,
                values
            )

            if r2 >= r2_min:

                score = len(current) * r2

                lines.append({
                    "slope": float(slope),
                    "intercept": float(intercept),
                    "points": current,
                    "r2": float(r2),
                    "score": float(score)
                })

        i += 1

    return lines


# =========================================================
# MAIN EXTRACTION METHOD
# =========================================================
def extract_market_structure(
        df,
        window=3,
        min_move=0.005,
        buffer_pct=0.001,
        min_touches=2):

    highs = df['High'].to_numpy()
    lows = df['Low'].to_numpy()

    # =====================================================
    # SWINGS
    # =====================================================
    swing_lows, swing_highs = swing_points(
        highs,
        lows,
        window
    )

    swing_lows = filter_swings(
        swing_lows,
        lows,
        min_move
    )

    swing_highs = filter_swings(
        swing_highs,
        highs,
        min_move
    )

    # =====================================================
    # SUPPORTS
    # =====================================================
    supports = []

    used_supports = []

    for idx in swing_lows:

        level = lows[idx]

        if not is_far_from_existing(
            level,
            used_supports,
            buffer_pct
        ):
            continue

        touches = count_touches(
            lows,
            idx,
            level,
            buffer_pct
        )

        if len(touches) >= min_touches:

            used_supports.append(level)

            supports.append({
                "index": idx,
                "price": float(level),
                "touches": touches
            })

    # =====================================================
    # RESISTANCE
    # =====================================================
    resistances = []

    used_resistance = []

    for idx in swing_highs:

        level = highs[idx]

        if not is_far_from_existing(
            level,
            used_resistance,
            buffer_pct
        ):
            continue

        touches = count_touches(
            highs,
            idx,
            level,
            buffer_pct
        )

        if len(touches) >= min_touches:

            used_resistance.append(level)

            resistances.append({
                "index": idx,
                "price": float(level),
                "touches": touches
            })

    # =====================================================
    # TRENDLINES
    # =====================================================
    support_trendlines = build_trendlines(
        swing_lows,
        lows
    )

    resistance_trendlines = build_trendlines(
        swing_highs,
        highs
    )

    # =====================================================
    # RETURN
    # =====================================================
    return {

        "swing_lows": [
            {
                "index": i,
                "price": float(lows[i])
            }
            for i in swing_lows
        ],

        "swing_highs": [
            {
                "index": i,
                "price": float(highs[i])
            }
            for i in swing_highs
        ],

        "supports": supports,

        "resistances": resistances,

        "support_trendlines": support_trendlines,

        "resistance_trendlines": resistance_trendlines
    }


# =========================================================
# ORDERED SWING SEQUENCE
# =========================================================
def get_swing_sequence(df, window=3, min_move=0.005):
    """
    Returns swing highs and lows merged and sorted by bar index,
    alternating so no two consecutive points are the same type.

    Each entry:
        { "index": int, "price": float, "type": "high" | "low" }
    """

    highs = df['High'].to_numpy()
    lows  = df['Low'].to_numpy()

    # --- detect raw swings ---
    raw_lows, raw_highs = swing_points(highs, lows, window)
    raw_lows  = filter_swings(raw_lows,  lows,  min_move)
    raw_highs = filter_swings(raw_highs, highs, min_move)

    # --- tag and merge ---
    points = (
        [{"index": i, "price": float(lows[i]),  "type": "low"}  for i in raw_lows] +
        [{"index": i, "price": float(highs[i]), "type": "high"} for i in raw_highs]
    )

    points.sort(key=lambda p: p["index"])

    # --- enforce alternation: keep only the extreme when two of the
    #     same type are adjacent (e.g. two highs → keep the higher one) ---
    alternated = []

    for p in points:

        if not alternated:
            alternated.append(p)
            continue

        last = alternated[-1]

        if p["type"] == last["type"]:
            # same type → keep the more extreme one
            if p["type"] == "high":
                if p["price"] > last["price"]:
                    alternated[-1] = p
            else:
                if p["price"] < last["price"]:
                    alternated[-1] = p
        else:
            alternated.append(p)

    return alternated


# =========================================================
# SWING ZONES  (delegates to Structure/Highs_Lows.py)
# =========================================================
def get_swing_zones(df, window=3, significance=0.005, confirm_pct=0.01):
    """
    Returns confirmed swings and their rectangle zones.
    Delegates entirely to Structure.Highs_Lows so logic lives in one place.

    Returns:
        swings : list of { index, price, type }
        zones  : list of { type, left, right, top, bottom, broken }
    """
    swings = get_confirmed_swings(df, window=window,
                                  significance=significance,
                                  confirm_pct=confirm_pct)
    zones  = build_swing_zones(df, swings)
    return swings, zones


# =========================================================
# PDH / PDL  (direct yfinance fetch, dashboard-safe)
# =========================================================
def get_pdh_pdl(ticker):
    """
    Returns (prev_high, prev_low) for *ticker* using a direct
    yfinance fetch — safe to call from the dashboard where
    MARKET_DATA may not be populated.

    yfinance 1d data has a timezone-naive UTC index.
    A candle for "today" is stored as 2026-06-24 00:00 UTC, but
    when it's 09:30 IST that is still 2026-06-23 UTC — so a naive
    date comparison lets today's partial candle slip through.
    Fix: convert the index to IST before comparing dates.
    """
    try:
        import yfinance as yf
        import pandas as pd

        df = yf.download(
            ticker,
            interval="1d",
            period="5d",
            progress=False,
            auto_adjust=True,
        )

        if df is None or df.empty:
            return None, None

        # Flatten MultiIndex columns produced by yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        # Drop rows where OHLC are all NaN
        df = df.dropna(subset=["High", "Low", "Open", "Close"])

        if df.empty:
            return None, None

        # Convert index to IST so date comparisons align with the
        # Indian trading calendar — yfinance stores 1d timestamps as
        # UTC midnight, which is behind IST by +05:30.
        IST = "Asia/Kolkata"
        if df.index.tz is None:
            idx_ist = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            idx_ist = df.index.tz_convert(IST)

        today_ist = pd.Timestamp.now(tz=IST).date()

        # Keep only candles whose IST date is strictly before today
        prev_df = df[idx_ist.date < today_ist]

        if prev_df.empty:
            return None, None

        prev = prev_df.iloc[-1]   # last fully-closed trading day
        return float(prev["High"]), float(prev["Low"])

    except Exception as e:
        import logging
        logging.warning(f"get_pdh_pdl({ticker}) failed: {e}")
        return None, None
