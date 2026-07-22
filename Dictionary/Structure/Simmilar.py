"""
Structure/Simmilar.py
=====================
Two independent tools:

  1. find_pattern(df, pattern_def)
     ─ User-defined multi-candle pattern matcher.
       Describe each candle with relative size / direction / overlap rules
       and get back every bar index where the full sequence matches.

  2. find_liquidity_sweeps(df, swings, ...)
     ─ Algorithmic liquidity-sweep detector.
       A sweep = wick pierces a prior swing high/low  AND  candle closes
       back on the originating side → price grabbed liquidity but rejected.

  Both are purely analytical (no side-effects) and return plain lists so
  they can be consumed by any dashboard or plotting routine.

  A self-contained trail-run at the bottom demonstrates both with a dark
  matplotlib chart identical in style to Highs_Lows.py.
"""

import os
import sys
import logging
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Data_Manager import get_data
from Dictionary.Structure.Highs_Lows import get_confirmed_swings


# =========================================================
# SECTION 1 — USER-DEFINED CANDLE PATTERN MATCHER
# =========================================================

# ─── candle feature extractor ────────────────────────────

def _candle_features(opens, highs, lows, closes, i):
    """
    Compute per-candle metrics for bar i.

    Returns a dict:
      body        – absolute body size
      body_pct    – body / full_range
      upper_wick  – size of upper wick
      lower_wick  – size of lower wick
      full_range  – high - low
      direction   – "bull" | "bear" | "doji"
      open, high, low, close
    """
    o, h, l, c = opens[i], highs[i], lows[i], closes[i]
    full_range  = h - l
    body        = abs(c - o)
    body_pct    = body / full_range if full_range > 0 else 0.0
    upper_wick  = h - max(o, c)
    lower_wick  = min(o, c) - l

    if body_pct < 0.05:
        direction = "doji"
    elif c >= o:
        direction = "bull"
    else:
        direction = "bear"

    return {
        "body"       : body,
        "body_pct"   : body_pct,
        "upper_wick" : upper_wick,
        "lower_wick" : lower_wick,
        "full_range" : full_range,
        "direction"  : direction,
        "open"       : o,
        "high"       : h,
        "low"        : l,
        "close"      : c,
    }


# ─── single candle rule evaluator ────────────────────────

def _candle_matches(feat, rule):
    """
    Check whether a candle's feature dict satisfies one rule dict.

    Supported rule keys (all optional — omit to skip that check):

      direction   : "bull" | "bear" | "doji" | "any"

      size        : "big" | "medium" | "small" | "any"
                    thresholds — big: body_pct > 0.55
                                 medium: 0.25 < body_pct <= 0.55
                                 small: body_pct <= 0.25

      body_pct_min / body_pct_max : float  (0 – 1)

      has_upper_wick  : bool  — True → upper_wick > 0.05 * full_range
      has_lower_wick  : bool  — True → lower_wick > 0.05 * full_range

      upper_wick_min_pct : float   — upper_wick >= X * full_range
      lower_wick_min_pct : float   — lower_wick >= X * full_range
    """

    # ── direction ──
    req_dir = rule.get("direction", "any")
    if req_dir != "any" and feat["direction"] != req_dir:
        return False

    # ── size ──
    req_size = rule.get("size", "any")
    bp = feat["body_pct"]
    if req_size == "big"    and bp <= 0.55:  return False
    if req_size == "medium" and not (0.25 < bp <= 0.55): return False
    if req_size == "small"  and bp > 0.25:   return False

    # ── body_pct bounds ──
    if bp < rule.get("body_pct_min", 0.0):  return False
    if bp > rule.get("body_pct_max", 1.0):  return False

    # ── wick presence ──
    fr = feat["full_range"] or 1e-9
    if rule.get("has_upper_wick") is True  and feat["upper_wick"] <= 0.05 * fr: return False
    if rule.get("has_upper_wick") is False and feat["upper_wick"] >  0.05 * fr: return False
    if rule.get("has_lower_wick") is True  and feat["lower_wick"] <= 0.05 * fr: return False
    if rule.get("has_lower_wick") is False and feat["lower_wick"] >  0.05 * fr: return False

    # ── wick minimum pct ──
    if feat["upper_wick"] < rule.get("upper_wick_min_pct", 0.0) * fr: return False
    if feat["lower_wick"] < rule.get("lower_wick_min_pct", 0.0) * fr: return False

    return True


# ─── cross-candle relationship evaluator ─────────────────

def _sequence_relations_match(feats, relations):
    """
    Validate optional cross-candle rules across the whole sequence.

    relations is a list of dicts, each with:
      candle_a  : int   – 0-based index in feats (the earlier candle)
      candle_b  : int   – 0-based index in feats (the later candle)
      rule      : one of the strings below

    Supported rules:
      "b_closes_above_a_low"    – feats[b].close > feats[a].low
      "b_closes_below_a_high"   – feats[b].close < feats[a].high
      "b_sweeps_a_low"          – feats[b].low < feats[a].low
                                  AND feats[b].close > feats[a].low
      "b_sweeps_a_high"         – feats[b].high > feats[a].high
                                  AND feats[b].close < feats[a].high
      "b_body_inside_a"         – b's body range sits within a's full range
      "b_smaller_than_a"        – feats[b].body < feats[a].body
      "b_larger_than_a"         – feats[b].body > feats[a].body
    """
    for rel in relations:
        a  = feats[rel["candle_a"]]
        b  = feats[rel["candle_b"]]
        r  = rel["rule"]

        if r == "b_closes_above_a_low":
            if not (b["close"] > a["low"]):             return False
        elif r == "b_closes_below_a_high":
            if not (b["close"] < a["high"]):            return False
        elif r == "b_sweeps_a_low":
            if not (b["low"] < a["low"] and
                    b["close"] > a["low"]):             return False
        elif r == "b_sweeps_a_high":
            if not (b["high"] > a["high"] and
                    b["close"] < a["high"]):            return False
        elif r == "b_body_inside_a":
            b_body_lo = min(b["open"], b["close"])
            b_body_hi = max(b["open"], b["close"])
            if not (b_body_lo >= a["low"] and
                    b_body_hi <= a["high"]):            return False
        elif r == "b_smaller_than_a":
            if not (b["body"] < a["body"]):             return False
        elif r == "b_larger_than_a":
            if not (b["body"] > a["body"]):             return False

    return True


# ─── public API ──────────────────────────────────────────

def find_pattern(df, pattern_def):
    """
    Scan df for every occurrence of a user-defined candle sequence.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV dataframe (columns: Open, High, Low, Close, Volume).

    pattern_def : dict
        {
          "candles"   : [ rule_dict, ... ],   # one rule per candle in sequence
          "relations" : [ rel_dict,  ... ],   # optional cross-candle rules
          "label"     : str                   # human-readable name (optional)
        }

    Returns
    -------
    list of dict:
        {
          "start_idx" : int   – bar index of the first candle in the match
          "end_idx"   : int   – bar index of the last candle in the match
          "bars"      : list  – all bar indices in the sequence
          "label"     : str
        }

    Example — big-bear + small-bull that sweeps the bear's low:
    ─────────────────────────────────────────────────────────────
    pattern_def = {
        "label"   : "Bear + Sweep Low",
        "candles" : [
            {"direction": "bear", "size": "big"},
            {"direction": "bull", "size": "small"},
        ],
        "relations": [
            {"candle_a": 0, "candle_b": 1, "rule": "b_sweeps_a_low"},
        ],
    }
    """
    candle_rules = pattern_def.get("candles", [])
    relations    = pattern_def.get("relations", [])
    label        = pattern_def.get("label", "pattern")
    n_candles    = len(candle_rules)

    if n_candles == 0:
        logging.warning("find_pattern: empty candle list.")
        return []

    opens  = df["Open"].to_numpy()
    highs  = df["High"].to_numpy()
    lows   = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    n      = len(df)

    matches = []

    for start in range(n - n_candles + 1):

        feats = [
            _candle_features(opens, highs, lows, closes, start + k)
            for k in range(n_candles)
        ]

        # per-candle rules
        if not all(_candle_matches(feats[k], candle_rules[k])
                   for k in range(n_candles)):
            continue

        # cross-candle relations
        if relations and not _sequence_relations_match(feats, relations):
            continue

        matches.append({
            "start_idx" : start,
            "end_idx"   : start + n_candles - 1,
            "bars"      : list(range(start, start + n_candles)),
            "label"     : label,
        })

    logging.info(f"find_pattern [{label}]: {len(matches)} matches found.")
    return matches


# =========================================================
# SECTION 2 — LIQUIDITY SWEEP DETECTOR
# =========================================================

def find_liquidity_sweeps(df, swings, tolerance_pct=0.001, lookback=None):
    """
    Detect liquidity sweeps against confirmed swing highs / lows.

    A SWEEP-LOW occurs when:
      • candle wick dips BELOW a prior swing-low  (low < swing.price)
      • candle CLOSES ABOVE the swing-low         (close > swing.price * (1 - tol))
      → price collected sell-side liquidity then rejected upward

    A SWEEP-HIGH occurs when:
      • candle wick pushes ABOVE a prior swing-high (high > swing.price)
      • candle CLOSES BELOW the swing-high          (close < swing.price * (1 + tol))
      → price collected buy-side liquidity then rejected downward

    Parameters
    ----------
    df          : pd.DataFrame   OHLCV
    swings      : list of dict   output of get_confirmed_swings()
                  each: { "index": int, "price": float, "type": "high"|"low" }
    tolerance_pct : float        close must be within this % of the swing level
                                 (default 0.1 % — tight filter)
    lookback    : int | None     only consider swings formed within this many
                                 bars before the sweep candle; None = unlimited

    Returns
    -------
    list of dict:
      {
        "bar_idx"     : int    – index of the sweep candle in df
        "sweep_type"  : "sweep_low" | "sweep_high"
        "swing_price" : float  – the swing level that was swept
        "swing_idx"   : int    – bar index of the origin swing
        "wick_extent" : float  – how far the wick went beyond the level
        "close"       : float  – close of the sweep candle
      }
    """
    opens  = df["Open"].to_numpy()
    highs  = df["High"].to_numpy()
    lows   = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    n      = len(df)

    sweeps = []

    for s in swings:

        swing_idx   = s["index"]
        swing_price = s["price"]
        swing_type  = s["type"]

        # scan bars AFTER the swing formed
        search_start = swing_idx + 1
        search_end   = n

        if lookback is not None:
            search_end = min(n, swing_idx + 1 + lookback)

        for i in range(search_start, search_end):

            if swing_type == "low":
                # 1. wick dips below the swing low
                # 2. close recovers above (within tolerance)
                # 3. open is below the level OR lower wick touches/breaches it
                wick_below  = lows[i]   <  swing_price
                close_above = closes[i] >  swing_price * (1 - tolerance_pct)
                open_below  = opens[i]  <  swing_price
                wick_touch  = lows[i]  <=  swing_price * (1 + tolerance_pct)

                if (wick_below and close_above and (open_below or wick_touch)):

                    sweeps.append({
                        "bar_idx"     : i,
                        "sweep_type"  : "sweep_low",
                        "swing_price" : swing_price,
                        "swing_idx"   : swing_idx,
                        "wick_extent" : swing_price - lows[i],
                        "close"       : float(closes[i]),
                    })
                    break   # one sweep per swing is enough

            else:  # "high"
                # 1. wick pushes above the swing high
                # 2. close rejects back below (within tolerance)
                # 3. open is above the level OR upper wick touches/breaches it
                wick_above  = highs[i]  >  swing_price
                close_below = closes[i] <  swing_price * (1 + tolerance_pct)
                open_above  = opens[i]  >  swing_price
                wick_touch  = highs[i] >=  swing_price * (1 - tolerance_pct)

                if (wick_above and close_below and (open_above or wick_touch)):

                    sweeps.append({
                        "bar_idx"     : i,
                        "sweep_type"  : "sweep_high",
                        "swing_price" : swing_price,
                        "swing_idx"   : swing_idx,
                        "wick_extent" : highs[i] - swing_price,
                        "close"       : float(closes[i]),
                    })
                    break

    logging.info(f"find_liquidity_sweeps: {len(sweeps)} sweeps detected.")
    return sweeps


# =========================================================
# TRAIL RUN — liquidity sweeps + VWAP plot
# =========================================================

if __name__ == "__main__":

    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import Rectangle
    from Data_Manager import Download, download_daily_all
    from Dictionary.Indicators.VWAP import VWAP
    from Dictionary.Indicators.EMA import EMA

    # ── config ──
    TICKER   = "BLUESTONE.NS"
    INTERVAL = "15m"

    Download([TICKER], "2d")
    download_daily_all([TICKER])

    df = get_data(TICKER, INTERVAL)
    if df is None or df.empty:
        print(f"No data for {TICKER}.")
        raise SystemExit

    opens  = df["Open"].to_numpy()
    highs  = df["High"].to_numpy()
    lows   = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    x_vals = np.arange(len(df))
    last_x = len(df) - 1

    # ── confirmed swings ──
    swings = get_confirmed_swings(df, window=3, significance=0.005, confirm_pct=0.01)

    # ── liquidity sweeps ──
    sweeps = find_liquidity_sweeps(df, swings, tolerance_pct=0.002)

    # ── VWAP ──
    vwap_series = VWAP(TICKER, INTERVAL)
    vwap_vals   = vwap_series.reindex(df.index).to_numpy().astype(float)

    # ── 5 EMA ──
    ema5_series = EMA(TICKER, 5, INTERVAL)
    ema5_vals   = ema5_series.reindex(df.index).to_numpy().astype(float)

    # =========================================================
    # PLOT
    # =========================================================

    BULL_C     = "#26a69a"
    BEAR_C     = "#ef5350"
    SWEEP_LOW  = "#00e676"    # bright green  — sweep low
    SWEEP_HIGH = "#ff1744"    # bright red    — sweep high
    SWING_HI_C = "#ef5350"
    SWING_LO_C = "#26a69a"
    VWAP_CLR   = "#ce93d8"    # purple        — VWAP
    EMA5_CLR   = "#ffd54f"    # amber         — 5 EMA

    fig, ax = plt.subplots(figsize=(18, 8))
    fig.patch.set_facecolor("#0f0f0f")
    ax.set_facecolor("#141414")
    fig.suptitle(
        f"{TICKER}  {INTERVAL}  —  Liquidity Sweeps  +  VWAP",
        fontsize=13, color="#e0e0e0", fontweight="bold"
    )

    # ── candlesticks ──
    for i in x_vals:
        is_bull = closes[i] >= opens[i]
        color   = BULL_C if is_bull else BEAR_C
        body_lo = min(opens[i], closes[i])
        body_hi = max(opens[i], closes[i])
        body_h  = body_hi - body_lo or (highs[i] - lows[i]) * 0.001

        ax.plot([i, i], [lows[i], highs[i]],
                color=color, linewidth=0.8, zorder=2)
        ax.add_patch(Rectangle(
            (i - 0.35, body_lo), 0.70, body_h,
            facecolor=color, edgecolor=color,
            linewidth=0.5, zorder=3
        ))

    # ── VWAP — segment per day to avoid cross-day joins ──
    IST = "Asia/Kolkata"
    try:
        idx_ist   = df.index.tz_convert(IST) if df.index.tz else df.index.tz_localize("UTC").tz_convert(IST)
        bar_dates = idx_ist.date
    except Exception:
        bar_dates = df.index.date

    current_day  = None
    seg_x, seg_v = [], []

    for i in x_vals:
        d = bar_dates[i]
        if d != current_day:
            if len(seg_x) > 1:
                ax.plot(seg_x, seg_v, color=VWAP_CLR, linewidth=1.2,
                        alpha=0.85, zorder=6)
            seg_x, seg_v = [], []
            current_day  = d
        if not np.isnan(vwap_vals[i]):
            seg_x.append(i)
            seg_v.append(vwap_vals[i])

    if len(seg_x) > 1:   # flush last segment
        ax.plot(seg_x, seg_v, color=VWAP_CLR, linewidth=1.2,
                alpha=0.85, zorder=6)

    # ── 5 EMA ──
    valid_mask = ~np.isnan(ema5_vals)
    ax.plot(x_vals[valid_mask], ema5_vals[valid_mask],
            color=EMA5_CLR, linewidth=1.1, alpha=0.90,
            label="5 EMA", zorder=5)

    # ── swing markers ──
    for s in swings:
        clr = SWING_HI_C if s["type"] == "high" else SWING_LO_C
        ax.scatter(s["index"], s["price"],
                   color=clr, marker="D", s=50, zorder=8, alpha=0.7)

    # ── liquidity sweep markers ──
    for sw in sweeps:
        bi  = sw["bar_idx"]
        si  = sw["swing_idx"]
        sp  = sw["swing_price"]
        is_low_sweep = sw["sweep_type"] == "sweep_low"
        clr = SWEEP_LOW if is_low_sweep else SWEEP_HIGH

        # dashed horizontal from swing to sweep candle
        ax.plot([si, bi], [sp, sp],
                color=clr, linewidth=0.9,
                linestyle="--", alpha=0.65, zorder=6)

        # arrow + label
        if is_low_sweep:
            ax.annotate(
                "", xy=(bi, lows[bi]),
                xytext=(bi, lows[bi] - sw["wick_extent"] * 3.5),
                arrowprops=dict(arrowstyle="->", color=clr, lw=1.4),
                zorder=10
            )
            ax.text(bi, lows[bi] - sw["wick_extent"] * 3.8,
                    "SL", ha="center", va="top",
                    fontsize=6.5, color=clr, fontweight="bold", zorder=11)
        else:
            ax.annotate(
                "", xy=(bi, highs[bi]),
                xytext=(bi, highs[bi] + sw["wick_extent"] * 3.5),
                arrowprops=dict(arrowstyle="->", color=clr, lw=1.4),
                zorder=10
            )
            ax.text(bi, highs[bi] + sw["wick_extent"] * 3.8,
                    "SH", ha="center", va="bottom",
                    fontsize=6.5, color=clr, fontweight="bold", zorder=11)

    # ── X axis ──
    n_ticks  = min(14, len(df))
    tick_pos = np.linspace(0, last_x, n_ticks, dtype=int)
    tick_lbl = [df.index[i].strftime("%d %b\n%H:%M") for i in tick_pos]
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_lbl, fontsize=7, color="#aaaaaa")
    ax.set_xlim(-1, last_x + 2)

    # ── legend ──
    legend_handles = [
        mpatches.Patch(color=SWEEP_LOW,  alpha=0.85, label="Sweep Low  (SL)"),
        mpatches.Patch(color=SWEEP_HIGH, alpha=0.85, label="Sweep High (SH)"),
        mpatches.Patch(color=SWING_HI_C, alpha=0.60, label="Swing High"),
        mpatches.Patch(color=SWING_LO_C, alpha=0.60, label="Swing Low"),
        mpatches.Patch(color=VWAP_CLR,   alpha=0.85, label="VWAP"),
        mpatches.Patch(color=EMA5_CLR,   alpha=0.90, label="5 EMA"),
    ]
    ax.legend(
        handles=legend_handles, fontsize=8,
        facecolor="#1e1e1e", edgecolor="#444444",
        labelcolor="#e0e0e0", loc="upper left"
    )

    ax.tick_params(axis="y", colors="#aaaaaa", labelsize=8)
    ax.set_ylabel("Price", color="#aaaaaa", fontsize=9)
    ax.grid(True, alpha=0.12, color="#444444", linewidth=0.5)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333333")

    plt.tight_layout()
    plt.show()
