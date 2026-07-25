"""
Structure/Demand_Zones.py
=========================
Detects **demand zones** (strong buyer concentration) and **supply zones**
(strong seller concentration) that have been revisited more than once —
i.e., price returned to the zone at least twice, confirming it as a
high-activity institutional area.

Core logic
----------
1. Find the "base" — a tight consolidation of N candles (low body / range)
   just before a strong impulsive move (big-body candle).
2. Build a price band from the base's high / low.
3. Scan forward: count how many times subsequent candles *enter* the zone
   (high ≥ zone_bottom and low ≤ zone_top) without fully closing through it.
4. Only keep zones that were touched ≥ 2 times  (first entry = creation,
   second entry = first re-test, etc.) and have NOT been violated (close
   fully outside the zone).
5. Repeat for all three timeframes: "1d", "4h", "15m".

Public API
----------
detect_demand_zones(df, zone_type, ...)  → list[dict]
    zone_type : "demand" | "supply" | "both"

get_demand_zones_multi(ticker, ...)      → dict[str, list[dict]]
    Returns {"1d": [...], "4h": [...], "15m": [...]}

plot_demand_zones(df, zones, ticker, timeframe)
    Dark-theme candlestick chart with zone overlays.

plot_demand_zones_multi(ticker, ...)
    One figure with three stacked subplots — one per timeframe.
"""

import logging
import numpy as np
import pandas as pd

from Data_Manager import get_data


# =========================================================
# CONSTANTS
# =========================================================

_INTERVALS       = ("1d", "4h", "15m")

# Zone construction defaults
_BASE_LOOKBACK   = 3        # candles to look back for the base
_IMPULSE_RATIO   = 1.6      # impulse body must be >= this × avg base body
_BASE_BODY_MAX   = 0.45     # base candles: body/range must be <= this
_ZONE_TOLERANCE  = 0.003    # 0.3 % band extension above/below zone edges
_MIN_TOUCHES     = 2        # minimum revisits to keep the zone
_VIOLATION_PCT   = 0.003    # zone is violated if candle CLOSES beyond edge
                            # by more than this fraction


# =========================================================
# HELPERS
# =========================================================

def _body_ratio(o: float, h: float, l: float, c: float) -> float:
    full_range = h - l
    return abs(c - o) / full_range if full_range > 0 else 0.0


def _to_ist(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    if index.tz is None:
        return index.tz_localize("UTC").tz_convert("Asia/Kolkata")
    return index.tz_convert("Asia/Kolkata")


# =========================================================
# CORE DETECTION
# =========================================================

def detect_demand_zones(
    df:              pd.DataFrame,
    zone_type:       str   = "both",
    base_lookback:   int   = _BASE_LOOKBACK,
    impulse_ratio:   float = _IMPULSE_RATIO,
    base_body_max:   float = _BASE_BODY_MAX,
    zone_tolerance:  float = _ZONE_TOLERANCE,
    min_touches:     int   = _MIN_TOUCHES,
    violation_pct:   float = _VIOLATION_PCT,
) -> list[dict]:
    """
    Detect demand / supply zones where strong buyer or seller activity was
    observed more than once.

    Parameters
    ----------
    df            : OHLCV DataFrame with DatetimeIndex
    zone_type     : "demand" | "supply" | "both"
    base_lookback : number of candles that form the base consolidation
    impulse_ratio : how much bigger (body-wise) the trigger candle must be
                    compared to the average base-candle body
    base_body_max : maximum body/range ratio for a candle to be part of the base
    zone_tolerance: fractional band added to zone edges (default 0.3 %)
    min_touches   : minimum number of times price must re-enter the zone
    violation_pct : a close beyond the zone edge by this fraction marks it violated

    Returns
    -------
    List of dicts:
        {
          "type"      : "demand" | "supply",
          "zone_top"  : float,
          "zone_bot"  : float,
          "left"      : int,    -- bar index where zone was formed
          "touches"   : int,    -- total revisits (including creation)
          "violated"  : bool,
          "fresh"     : bool,   -- True if last touch was a bounce (not violation)
        }
    """
    if df is None or len(df) < base_lookback + 2:
        logging.warning("detect_demand_zones: dataframe too short.")
        return []

    opens  = df["Open"].to_numpy(dtype=np.float64)
    highs  = df["High"].to_numpy(dtype=np.float64)
    lows   = df["Low"].to_numpy(dtype=np.float64)
    closes = df["Close"].to_numpy(dtype=np.float64)
    n      = len(df)

    want_demand = zone_type in ("demand", "both")
    want_supply = zone_type in ("supply", "both")

    zones: list[dict] = []

    # ── scan for impulse candles that follow a base ──────────────
    for i in range(base_lookback, n - 1):

        # ── check base candles i-base_lookback … i-1 ──
        base_slice = range(i - base_lookback, i)
        base_bodies = [
            abs(closes[j] - opens[j]) for j in base_slice
        ]
        avg_base_body = sum(base_bodies) / len(base_bodies) if base_bodies else 0

        # All base candles must be "tight" (small relative body)
        base_valid = all(
            _body_ratio(opens[j], highs[j], lows[j], closes[j]) <= base_body_max
            for j in base_slice
        )
        if not base_valid:
            continue

        # ── impulse candle at index i ──
        imp_body = abs(closes[i] - opens[i])
        imp_br   = _body_ratio(opens[i], highs[i], lows[i], closes[i])

        if avg_base_body == 0 or imp_body < impulse_ratio * avg_base_body:
            continue
        if imp_br < 0.40:          # impulse must be a strong-body candle
            continue

        imp_bull = closes[i] > opens[i]

        # ── zone boundaries from the base ──────────────────────
        base_high = max(highs[j]  for j in base_slice)
        base_low  = min(lows[j]   for j in base_slice)
        band      = (base_high - base_low) * zone_tolerance
        zone_top  = round(base_high + band, 2)
        zone_bot  = round(base_low  - band, 2)

        if zone_top <= zone_bot:
            continue

        # ── classify zone type ──────────────────────────────────
        #   demand (buyers) → impulse is BULLISH (price launches up)
        #   supply (sellers)→ impulse is BEARISH (price drops away)
        if imp_bull and not want_demand:
            continue
        if not imp_bull and not want_supply:
            continue

        z_type = "demand" if imp_bull else "supply"

        # ── forward scan: count touches & check violation ───────
        touches   = 1      # the formation impulse itself counts as touch 1
        violated  = False
        last_exit = i      # last bar that was inside or just left the zone

        for k in range(i + 1, n):
            enters_zone = highs[k] >= zone_bot and lows[k] <= zone_top

            if enters_zone:
                # Check violation: close fully through zone
                if z_type == "demand":
                    # violated if close drops significantly below zone bottom
                    if closes[k] < zone_bot * (1.0 - violation_pct):
                        violated = True
                        break
                else:  # supply
                    # violated if close pushes significantly above zone top
                    if closes[k] > zone_top * (1.0 + violation_pct):
                        violated = True
                        break

                # New touch: must have left the zone since last touch
                if k > last_exit + 1:
                    touches += 1

                last_exit = k

        if touches < min_touches:
            continue

        zones.append({
            "type"    : z_type,
            "zone_top": zone_top,
            "zone_bot": zone_bot,
            "left"    : i - base_lookback,   # start of base formation
            "touches" : touches,
            "violated": violated,
            "fresh"   : not violated,
        })

    # ── deduplicate overlapping zones (keep highest-touch one) ──
    zones = _deduplicate_zones(zones, tolerance=zone_tolerance)

    logging.info(
        f"detect_demand_zones [{zone_type}]: "
        f"{len(zones)} zones found  "
        f"({sum(1 for z in zones if not z['violated'])} active)."
    )
    return zones


# =========================================================
# DEDUPLICATION
# =========================================================

def _deduplicate_zones(
    zones:     list[dict],
    tolerance: float = 0.005,
) -> list[dict]:
    """
    Merge zones whose price bands overlap by more than `tolerance`.
    When two zones overlap, keep the one with more touches; on a tie,
    keep the more recent (higher 'left' index).
    """
    if not zones:
        return []

    zones = sorted(zones, key=lambda z: z["zone_bot"])
    merged: list[dict] = [zones[0]]

    for curr in zones[1:]:
        prev = merged[-1]
        # check overlap: curr.bot < prev.top + tolerance
        overlap_threshold = prev["zone_top"] * (1.0 + tolerance)
        if curr["zone_bot"] <= overlap_threshold and curr["type"] == prev["type"]:
            # keep the one with more touches; tie → keep newer
            if curr["touches"] > prev["touches"] or (
                curr["touches"] == prev["touches"] and curr["left"] > prev["left"]
            ):
                merged[-1] = curr
        else:
            merged.append(curr)

    return merged


# =========================================================
# MULTI-INTERVAL  (1d / 4h / 15m)
# =========================================================

def get_demand_zones_multi(
    ticker:         str,
    zone_type:      str   = "both",
    base_lookback:  int   = _BASE_LOOKBACK,
    impulse_ratio:  float = _IMPULSE_RATIO,
    base_body_max:  float = _BASE_BODY_MAX,
    zone_tolerance: float = _ZONE_TOLERANCE,
    min_touches:    int   = _MIN_TOUCHES,
    violation_pct:  float = _VIOLATION_PCT,
) -> dict[str, list[dict]]:
    """
    Run demand/supply zone detection across all three standard timeframes.

    Parameters
    ----------
    ticker     : yfinance-style symbol, e.g. "RELIANCE.NS"
    zone_type  : "demand" | "supply" | "both"
    (all other params forwarded to detect_demand_zones)

    Returns
    -------
    {
        "1d"  : [ zone_dict, ... ],
        "4h"  : [ zone_dict, ... ],
        "15m" : [ zone_dict, ... ],
    }

    Each zone_dict:
        {
          "type"      : "demand" | "supply",
          "zone_top"  : float,
          "zone_bot"  : float,
          "left"      : int,
          "touches"   : int,
          "violated"  : bool,
          "fresh"     : bool,
        }
    """
    result: dict[str, list[dict]] = {}

    for interval in _INTERVALS:
        df = get_data(ticker, interval)

        if df is None or df.empty:
            logging.warning(
                f"get_demand_zones_multi [{ticker}|{interval}]: no data."
            )
            result[interval] = []
            continue

        zones = detect_demand_zones(
            df,
            zone_type      = zone_type,
            base_lookback  = base_lookback,
            impulse_ratio  = impulse_ratio,
            base_body_max  = base_body_max,
            zone_tolerance = zone_tolerance,
            min_touches    = min_touches,
            violation_pct  = violation_pct,
        )

        result[interval] = zones

        logging.info(
            f"[{ticker}|{interval}]  {len(zones)} zones  "
            f"({sum(1 for z in zones if not z['violated'])} active)"
        )

    return result


# =========================================================
# RANGE SUMMARY  (price-level list per interval)
# =========================================================

def get_zone_ranges(
    zones_multi: dict[str, list[dict]],
    active_only: bool = True,
) -> dict[str, dict[str, list[dict]]]:
    """
    Convert the raw zone list into a compact price-range summary.

    Parameters
    ----------
    zones_multi : output of get_demand_zones_multi()
    active_only : if True, skip violated zones

    Returns
    -------
    {
        "1d": {
            "demand": [{"top": float, "bot": float, "touches": int}, ...],
            "supply": [{"top": float, "bot": float, "touches": int}, ...],
        },
        "4h": { ... },
        "15m": { ... },
    }
    """
    summary: dict[str, dict] = {}

    for interval, zones in zones_multi.items():
        demand_ranges = []
        supply_ranges = []

        for z in zones:
            if active_only and z["violated"]:
                continue
            entry = {
                "top"    : z["zone_top"],
                "bot"    : z["zone_bot"],
                "touches": z["touches"],
            }
            if z["type"] == "demand":
                demand_ranges.append(entry)
            else:
                supply_ranges.append(entry)

        summary[interval] = {
            "demand": demand_ranges,
            "supply": supply_ranges,
        }

    return summary


# =========================================================
# SINGLE-TIMEFRAME PLOT
# =========================================================

def plot_demand_zones(
    df:        pd.DataFrame,
    zones:     list[dict],
    ticker:    str = "",
    timeframe: str = "",
    ax=None,
) -> None:
    """
    Draw a dark-theme candlestick chart with demand / supply zone overlays.

    Parameters
    ----------
    df        : OHLCV DataFrame
    zones     : output of detect_demand_zones()
    ticker    : label for the chart title
    timeframe : e.g. "15m", "4h", "1d" — shown in title
    ax        : optional existing matplotlib Axes (used by multi-plot)
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.collections import LineCollection, PatchCollection
    from matplotlib.patches import Rectangle

    # ── colour palette ───────────────────────────────────
    BULL_C         = "#26a69a"
    BEAR_C         = "#ef5350"
    DEMAND_FILL    = "#26a69a"    # teal
    SUPPLY_FILL    = "#ef5350"    # red
    DEMAND_EDGE    = "#69f0ae"
    SUPPLY_EDGE    = "#ff6b6b"
    FILL_ALPHA     = 0.18
    FILL_ALPHA_VIO = 0.06
    EDGE_ALPHA     = 0.80
    TOUCH_CLR      = "#ffd54f"    # amber — touch-count label

    opens  = df["Open"].to_numpy()
    highs  = df["High"].to_numpy()
    lows   = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    x_vals = np.arange(len(df))
    last_x = len(df) - 1

    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(16, 7))
        fig.patch.set_facecolor("#0f0f0f")

    ax.set_facecolor("#141414")

    title = f"{ticker}  —  Demand / Supply Zones"
    if timeframe:
        title += f"  [{timeframe}]"
    ax.set_title(title, fontsize=11, color="#e0e0e0", fontweight="bold", pad=6)

    # ── vectorised candlestick ───────────────────────────
    bull_mask = closes >= opens
    body_lo   = np.where(bull_mask, opens,  closes)
    body_hi   = np.where(bull_mask, closes, opens)
    body_h    = np.where(
        body_hi - body_lo > 0,
        body_hi - body_lo,
        (highs - lows) * 0.001,
    )

    wick_segs = [[(i, lows[i]), (i, highs[i])] for i in x_vals]
    wick_cols = [BULL_C if bull_mask[i] else BEAR_C for i in x_vals]
    ax.add_collection(
        LineCollection(wick_segs, colors=wick_cols, linewidths=0.7, zorder=2)
    )

    bull_idx = x_vals[bull_mask]
    bear_idx = x_vals[~bull_mask]

    if len(bull_idx):
        ax.add_collection(PatchCollection(
            [Rectangle((i - 0.35, body_lo[i]), 0.70, body_h[i]) for i in bull_idx],
            facecolor=BULL_C, edgecolor=BULL_C, linewidth=0.4, zorder=3,
        ))
    if len(bear_idx):
        ax.add_collection(PatchCollection(
            [Rectangle((i - 0.35, body_lo[i]), 0.70, body_h[i]) for i in bear_idx],
            facecolor=BEAR_C, edgecolor=BEAR_C, linewidth=0.4, zorder=3,
        ))

    # ── zone rectangles ──────────────────────────────────
    for z in zones:
        is_demand = z["type"] == "demand"
        fill_clr  = DEMAND_FILL if is_demand else SUPPLY_FILL
        edge_clr  = DEMAND_EDGE if is_demand else SUPPLY_EDGE
        fa        = FILL_ALPHA_VIO if z["violated"] else FILL_ALPHA
        ea        = EDGE_ALPHA * (0.30 if z["violated"] else 1.0)

        left   = z["left"]
        right  = last_x          # extend zone to the right edge of chart
        width  = right - left
        height = z["zone_top"] - z["zone_bot"]

        # filled rectangle
        ax.add_patch(mpatches.Rectangle(
            (left, z["zone_bot"]), width, height,
            facecolor=fill_clr, alpha=fa,
            linewidth=0, zorder=4,
        ))

        # top and bottom edge lines
        ax.plot([left, right], [z["zone_top"], z["zone_top"]],
                color=edge_clr, lw=0.9, alpha=ea, zorder=5)
        ax.plot([left, right], [z["zone_bot"], z["zone_bot"]],
                color=edge_clr, lw=0.9, alpha=ea, zorder=5)

        # mid-point label with touch count
        mid_y = (z["zone_top"] + z["zone_bot"]) / 2
        label = (
            f"{'D' if is_demand else 'S'}  "
            f"{z['zone_bot']:.1f} – {z['zone_top']:.1f}  "
            f"(×{z['touches']})"
        )
        ax.text(
            left + 0.5, mid_y, label,
            color=TOUCH_CLR if not z["violated"] else "#555555",
            fontsize=6.5, va="center", ha="left", zorder=6,
        )

    # ── X-axis ticks ─────────────────────────────────────
    n_ticks  = min(12, len(df))
    tick_pos = np.linspace(0, last_x, n_ticks, dtype=int)
    tick_lbl = [df.index[i].strftime("%d %b\n%H:%M") for i in tick_pos]
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_lbl, fontsize=6.5, color="#aaaaaa")
    ax.set_xlim(-1, last_x + 2)
    ax.autoscale_view()

    # ── legend ───────────────────────────────────────────
    n_demand  = sum(1 for z in zones if z["type"] == "demand" and not z["violated"])
    n_supply  = sum(1 for z in zones if z["type"] == "supply" and not z["violated"])
    n_vio     = sum(1 for z in zones if z["violated"])

    handles = [
        mpatches.Patch(color=DEMAND_FILL, alpha=0.55, label=f"Demand  ({n_demand} active)"),
        mpatches.Patch(color=SUPPLY_FILL, alpha=0.55, label=f"Supply  ({n_supply} active)"),
    ]
    if n_vio:
        handles.append(
            mpatches.Patch(color="#888888", alpha=0.40, label=f"Violated ({n_vio})")
        )
    ax.legend(
        handles=handles, fontsize=7.5,
        facecolor="#1e1e1e", edgecolor="#444444",
        labelcolor="#e0e0e0", loc="upper left",
    )

    ax.tick_params(axis="y", colors="#aaaaaa", labelsize=7.5)
    ax.set_ylabel("Price", color="#aaaaaa", fontsize=8)
    ax.grid(True, alpha=0.11, color="#444444", linewidth=0.5)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333333")

    if standalone:
        plt.tight_layout()
        plt.show()


# =========================================================
# MULTI-TIMEFRAME PLOT  (1d / 4h / 15m stacked)
# =========================================================

def plot_demand_zones_multi(
    ticker:         str,
    zones_multi:    dict[str, list[dict]] | None = None,
    zone_type:      str   = "both",
    base_lookback:  int   = _BASE_LOOKBACK,
    impulse_ratio:  float = _IMPULSE_RATIO,
    base_body_max:  float = _BASE_BODY_MAX,
    zone_tolerance: float = _ZONE_TOLERANCE,
    min_touches:    int   = _MIN_TOUCHES,
    violation_pct:  float = _VIOLATION_PCT,
) -> None:
    """
    Render three stacked subplots — one per timeframe (1d, 4h, 15m) —
    each showing the candlestick chart with demand/supply zone overlays.

    Parameters
    ----------
    ticker      : yfinance-style symbol
    zones_multi : pre-computed output of get_demand_zones_multi();
                  if None, computed internally from MARKET_DATA
    (other params forwarded to get_demand_zones_multi if zones_multi is None)
    """
    import matplotlib.pyplot as plt

    if zones_multi is None:
        zones_multi = get_demand_zones_multi(
            ticker,
            zone_type      = zone_type,
            base_lookback  = base_lookback,
            impulse_ratio  = impulse_ratio,
            base_body_max  = base_body_max,
            zone_tolerance = zone_tolerance,
            min_touches    = min_touches,
            violation_pct  = violation_pct,
        )

    fig, axes = plt.subplots(
        nrows=3, ncols=1,
        figsize=(18, 18),
        constrained_layout=True,
    )
    fig.patch.set_facecolor("#0f0f0f")
    fig.suptitle(
        f"{ticker}  —  Demand / Supply Zones  ·  Multi-Timeframe",
        fontsize=14, color="#e0e0e0", fontweight="bold", y=1.005,
    )

    for ax, interval in zip(axes, _INTERVALS):
        df = get_data(ticker, interval)

        if df is None or df.empty:
            ax.set_facecolor("#141414")
            ax.text(
                0.5, 0.5, f"No data for {interval}",
                color="#888888", fontsize=11,
                ha="center", va="center",
                transform=ax.transAxes,
            )
            ax.set_title(f"[{interval}]  —  no data",
                         color="#666666", fontsize=10)
            continue

        zones = zones_multi.get(interval, [])
        plot_demand_zones(df, zones, ticker=ticker, timeframe=interval, ax=ax)

    plt.show()


# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    from Data_Manager import Download, download_daily_all

    TICKER = "POLYMED.NS"

    Download([TICKER], "30d")
    download_daily_all([TICKER])

    # ── compute zones for all three timeframes ──────────
    zones_multi = get_demand_zones_multi(TICKER, zone_type="both", min_touches=2)

    # ── compact price-range summary ─────────────────────
    ranges = get_zone_ranges(zones_multi, active_only=True)

    # for interval, r in ranges.items():
    #     print(f"\n{'─'*50}")
    #     print(f"  {interval}  Demand zones  ({len(r['demand'])} active)")
    #     for z in r["demand"]:
    #         print(f"    {z['bot']:.2f} – {z['top']:.2f}   touches={z['touches']}")
    #     print(f"  {interval}  Supply zones  ({len(r['supply'])} active)")
    #     for z in r["supply"]:
    #         print(f"    {z['bot']:.2f} – {z['top']:.2f}   touches={z['touches']}")

    # ── multi-timeframe plot ─────────────────────────────
    plot_demand_zones_multi(TICKER, zones_multi=zones_multi)
