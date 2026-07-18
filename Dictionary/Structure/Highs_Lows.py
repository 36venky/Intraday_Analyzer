import os
import logging
import numpy as np
import pandas as pd

from Data_Manager import *


# =========================================================
# PREVIOUS DAY LEVELS
# =========================================================

def previous_day_levels(ticker):
    """
    Returns (prev_high, prev_low) for the correct reference trading day.

    Time-aware logic (IST):
      - Before 09:00 AM  → market hasn't opened yet; yesterday's session is
                           incomplete/not yet relevant, so return the day
                           BEFORE yesterday (i.e. iloc[-2] of completed days).
      - 09:00 AM or later → yesterday's session is the valid reference day
                           (iloc[-1] of completed days).

    "Completed days" = all 1d candles whose IST date is strictly before
    today's IST date (yfinance never includes a partial today candle in
    period="1y" downloads, but we guard anyway).
    """
    from Data_Manager.data import MARKET_DATA

    raw = MARKET_DATA.get(ticker, {}).get("1d")

    if raw is None or raw.empty:
        logging.warning(f"{ticker} daily data unavailable or insufficient.")
        return None, None

    IST = "Asia/Kolkata"
    try:
        if raw.index.tz is None:
            idx_ist = raw.index.tz_localize("UTC").tz_convert(IST)
        else:
            idx_ist = raw.index.tz_convert(IST)
        now_ist   = pd.Timestamp.now(tz=IST)
        today_ist = now_ist.date()
    except Exception:
        now_ist   = pd.Timestamp.now()
        today_ist = now_ist.date()

    # All fully-closed daily candles (strictly before today)
    prev_df = raw[idx_ist.date < today_ist]

    if prev_df.empty:
        logging.warning(f"{ticker} no completed daily candles available.")
        return None, None

    # After 09:30 IST — check if live intraday data for today exists.
    #   - Live data present  → yesterday is the valid reference (iloc[-1])
    #   - No live data yet   → use day-before-yesterday (iloc[-2])
    # Before 09:30 IST      → market hasn't opened; use day-before-yesterday.
    market_open = now_ist.replace(hour=9, minute=30, second=0, microsecond=0)

    if now_ist >= market_open:
        # Check intraday data for a candle dated today
        intraday = MARKET_DATA.get(ticker, {}).get("15m")

        live_today = False
        if intraday is not None and not intraday.empty:
            try:
                if intraday.index.tz is None:
                    intra_ist = intraday.index.tz_localize("UTC").tz_convert(IST)
                else:
                    intra_ist = intraday.index.tz_convert(IST)
                live_today = any(d == today_ist for d in intra_ist.date)
            except Exception:
                live_today = False

        if live_today:
            ref = prev_df.iloc[-1]          # yesterday — live data confirmed
        else:
            # After 09:30 but no intraday candle yet; fall back one more day
            if len(prev_df) < 2:
                logging.warning(f"{ticker} not enough history for pre-market PDH/PDL.")
                return None, None
            ref = prev_df.iloc[-2]          # day before yesterday
    else:
        # Before 09:30 IST — market not open yet
        if len(prev_df) < 2:
            logging.warning(f"{ticker} not enough history for pre-open PDH/PDL.")
            return None, None
        ref = prev_df.iloc[-2]              # day before yesterday

    prev_high = float(ref["High"])
    prev_low  = float(ref["Low"])

    logging.info(
        f"{ticker} PDH/PDL ref date: {idx_ist[raw.index.get_loc(ref.name)] if hasattr(ref, 'name') else 'N/A'} "
        f"| High: {prev_high}, Low: {prev_low}"
    )
    return prev_high, prev_low


# =========================================================
# RAW SWING DETECTION
# =========================================================

def swing_points(highs, lows, window=3):
    """Detect local swing high/low indices using a rolling window."""
    swing_highs, swing_lows = [], []

    for i in range(window, len(highs) - window):
        if highs[i] == max(highs[i - window: i + window + 1]):
            swing_highs.append(i)
        if lows[i] == min(lows[i - window: i + window + 1]):
            swing_lows.append(i)

    return swing_lows, swing_highs


# =========================================================
# HELPERS
# =========================================================

def _keep_extreme(result, p):
    """Replace last point if same type and current is more extreme."""
    last = result[-1]
    if p["type"] == last["type"]:
        if p["type"] == "high" and p["price"] > last["price"]:
            result[-1] = p
        elif p["type"] == "low" and p["price"] < last["price"]:
            result[-1] = p
    else:
        result.append(p)


def _tag_points(highs, lows, highs_idx, lows_idx):
    """Tag and sort raw indices into a unified point list."""
    points = (
        [{"index": i, "price": float(lows[i]),  "type": "low"}  for i in lows_idx] +
        [{"index": i, "price": float(highs[i]), "type": "high"} for i in highs_idx]
    )
    points.sort(key=lambda p: p["index"])
    return points


# =========================================================
# SIGNIFICANT SWINGS  (0.5% consecutive dedup)
# =========================================================

def get_significant_swings(df, window=3, significance=0.005):
    """
    Merge consecutive same-type swings:
    - diff > significance  → keep both
    - diff <= significance → keep only the extreme
    """
    highs = df['High'].to_numpy()
    lows  = df['Low'].to_numpy()

    raw_lows_idx, raw_highs_idx = swing_points(highs, lows, window)
    points = _tag_points(highs, lows, raw_highs_idx, raw_lows_idx)

    if not points:
        return []

    result, i = [], 0
    while i < len(points):
        # collect consecutive same-type group
        group = [points[i]]
        while i + 1 < len(points) and points[i + 1]["type"] == points[i]["type"]:
            i += 1
            group.append(points[i])

        if len(group) == 1:
            result.append(group[0])
        else:
            significant = [group[0]]
            for curr in group[1:]:
                diff = abs(curr["price"] - significant[-1]["price"]) / significant[-1]["price"]
                if diff > significance:
                    significant.append(curr)
                else:
                    _keep_extreme(significant, curr)
            result.extend(significant)

        i += 1

    return result


# =========================================================
# CONFIRMED SWINGS  (1% follow-through + extreme dedup)
# =========================================================

def get_confirmed_swings(df, window=3, significance=0.005, confirm_pct=0.01):
    """
    Pipeline:
      1. get_significant_swings  — 0.5% consecutive dedup
      2. Keep only points where the immediate next opposing swing
         moves > confirm_pct (default 1%)
      3. Dedup remaining consecutive same-type → keep extreme

    Returns list of { "index", "price", "type" }
    """
    sig = get_significant_swings(df, window=window, significance=significance)

    # Step 2 — confirm by follow-through
    confirmed = []
    for i, point in enumerate(sig):
        for nxt in sig[i + 1:]:
            if nxt["type"] == point["type"]:
                continue
            diff = abs(nxt["price"] - point["price"]) / point["price"]
            if point["type"] == "high" and nxt["price"] < point["price"] and diff > confirm_pct:
                confirmed.append(point)
            elif point["type"] == "low" and nxt["price"] > point["price"] and diff > confirm_pct:
                confirmed.append(point)
            break

    # Step 3 — dedup consecutive same-type
    result = []
    for p in confirmed:
        if not result:
            result.append(p)
        else:
            _keep_extreme(result, p)

    return result


# =========================================================
# SWING ZONES  (rectangle from swing candle → breakout)
# =========================================================

def build_swing_zones(df, swings):
    """
    For each confirmed swing build a rectangle zone:

    SWING HIGH zone:
      - Top    = swing candle High
      - Bottom = close of the first bearish candle (within next 7 bars) whose
                 close is below the swing candle's 50% midpoint
                 Fallback: swing candle's own close
      - Left   = swing candle bar index
      - Right  = first bar (from swing+1) where close > top  (breakout above)
                 If never broken → extends to last bar

    SWING LOW zone:
      - Bottom = swing candle Low
      - Top    = close of the first bullish candle (within next 7 bars) whose
                 close is above the swing candle's 50% midpoint
                 Fallback: swing candle's own close
      - Left   = swing candle bar index
      - Right  = first bar (from swing+1) where close < bottom (breakout below)
                 If never broken → extends to last bar

    The zone is considered "broken" only by a candle CLOSE beyond the boundary,
    not just a wick.

    Returns list of dicts:
        {
            "type"    : "high" | "low"
            "left"    : int    – start bar index (swing candle)
            "right"   : int    – end bar index   (breakout bar or last bar)
            "top"     : float  – upper price boundary  (swing candle High)
            "bottom"  : float  – lower price boundary  (swing candle Low)
            "broken"  : bool   – True if zone was actually broken before last bar
        }
    """
    opens  = df["Open"].values
    closes = df["Close"].values
    highs  = df["High"].values
    lows   = df["Low"].values
    n      = len(df)

    ZONE_LOOKBACK = 7   # candles to search for the 50%-cross candle

    zones = []

    for s in swings:
        idx      = s["index"]
        sw_high  = float(highs[idx])
        sw_low   = float(lows[idx])
        midpoint = (sw_high + sw_low) / 2.0
        right    = n - 1
        broken   = False

        if s["type"] == "high":
            top = sw_high

            # Bottom = close of first bearish candle (within 7 bars) that
            # closes below the swing candle's 50% midpoint.
            # Fallback: swing candle's own close.
            bottom = float(closes[idx])
            for j in range(idx + 1, min(idx + 1 + ZONE_LOOKBACK, n)):
                if closes[j] < opens[j] and closes[j] < midpoint:
                    bottom = float(closes[j])
                    break

            # Extend right until a close breaks above top
            for j in range(idx + 1, n):
                if closes[j] > top:
                    right  = j
                    broken = True
                    break

        else:  # low
            bottom = sw_low

            # Top = close of first bullish candle (within 7 bars) that
            # closes above the swing candle's 50% midpoint.
            # Fallback: swing candle's own close.
            top = float(closes[idx])
            for j in range(idx + 1, min(idx + 1 + ZONE_LOOKBACK, n)):
                if closes[j] > opens[j] and closes[j] > midpoint:
                    top = float(closes[j])
                    break

            # Extend right until a close breaks below bottom
            for j in range(idx + 1, n):
                if closes[j] < bottom:
                    right  = j
                    broken = True
                    break

        zones.append({
            "type"  : s["type"],
            "left"  : idx,
            "right" : right,
            "top"   : top,
            "bottom": bottom,
            "broken": broken,
        })


    return zones



# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    import numpy as np
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import Rectangle
    from Data_Manager import Download

    tickers = ["BECTORFOOD.NS"]
    Download(tickers,"10d")
    download_daily_all(tickers)

    for ticker in tickers:

        df = get_data(ticker, "15m")
        if df is None or df.empty:
            print(f"{ticker} — no data.")
            continue

        swings = get_confirmed_swings(df, window=3, significance=0.005, confirm_pct=0.01)
        zones  = build_swing_zones(df, swings)

        opens  = df["Open"].to_numpy()
        highs  = df["High"].to_numpy()
        lows   = df["Low"].to_numpy()
        closes = df["Close"].to_numpy()
        x_vals = np.arange(len(df))
        last_x = len(df) - 1

        # ── colours ──
        BULL_C     = "#26a69a"   # teal  — bullish candle
        BEAR_C     = "#ef5350"   # red   — bearish candle
        HIGH_CLR   = "#ef5350"   # red   — swing high zone
        LOW_CLR    = "#26a69a"   # teal  — swing low zone
        FILL_A     = 0.18        # fill alpha for active zones
        FILL_A_BRK = 0.07        # fill alpha for broken zones
        EDGE_A     = 0.75
        PDH_CLR    = "#ffb74d"   # amber — previous day high
        PDL_CLR    = "#81d4fa"   # sky   — previous day low
        VLINE_CLR  = "#ffffff"   # white — previous-day boundary lines

        fig, ax = plt.subplots(figsize=(16, 7))
        fig.patch.set_facecolor("#0f0f0f")
        ax.set_facecolor("#141414")
        fig.suptitle(
            f"{ticker}  —  Swing High / Low Zones",
            fontsize=13, color="#e0e0e0", fontweight="bold"
        )

        # ── candlestick drawing (same style as FVG.py) ──
        for i in x_vals:
            is_bull = closes[i] >= opens[i]
            color   = BULL_C if is_bull else BEAR_C
            body_lo = min(opens[i], closes[i])
            body_hi = max(opens[i], closes[i])
            body_h  = body_hi - body_lo or (highs[i] - lows[i]) * 0.001  # doji guard

            # Wick
            ax.plot([i, i], [lows[i], highs[i]], color=color, linewidth=0.8, zorder=2)
            # Body
            ax.add_patch(Rectangle(
                (i - 0.35, body_lo), 0.70, body_h,
                facecolor=color, edgecolor=color, linewidth=0.5, zorder=3
            ))

        # ── previous-day vertical boundary lines ──
        # Follows the same reference-day logic as previous_day_levels():
        #   After 09:30 IST + live intraday candle exists → yesterday
        #   Otherwise (before 09:30, or no live data yet)  → day-before-yesterday
        IST = "Asia/Kolkata"
        try:
            if df.index.tz is None:
                idx_ist = df.index.tz_localize("UTC").tz_convert(IST)
            else:
                idx_ist = df.index.tz_convert(IST)
            now_ist   = pd.Timestamp.now(tz=IST)
            today_ist = now_ist.date()
        except Exception:
            idx_ist   = df.index
            now_ist   = pd.Timestamp.now()
            today_ist = now_ist.date()

        bar_dates  = idx_ist.date
        prev_dates = [d for d in sorted(set(bar_dates)) if d < today_ist]

        if prev_dates:
            market_open = now_ist.replace(hour=9, minute=30, second=0, microsecond=0)

            # Check if a today-dated intraday candle is present in df
            live_today = any(d == today_ist for d in bar_dates)

            if now_ist >= market_open and live_today:
                ref_day = prev_dates[-1]        # yesterday
            else:
                # Before 09:30, or after 09:30 but no live data yet
                ref_day = prev_dates[-2] if len(prev_dates) >= 2 else prev_dates[-1]

            prev_mask    = bar_dates == ref_day
            prev_indices = np.where(prev_mask)[0]
            if len(prev_indices) > 0:
                pd_start = int(prev_indices[0])
                pd_end   = int(prev_indices[-1])
                # left boundary — start of reference day
                ax.axvline(pd_start - 0.5, color=VLINE_CLR, linewidth=1.0,
                           linestyle="--", alpha=0.55, zorder=6)
                # right boundary — end of reference day
                ax.axvline(pd_end + 0.5, color=VLINE_CLR, linewidth=1.0,
                           linestyle="--", alpha=0.55, zorder=6)
                # label the section
                label_y = highs.max()
                ax.text(
                    (pd_start + pd_end) / 2, label_y,
                    f"Prev Day  {ref_day.strftime('%d %b')}",
                    color=VLINE_CLR, fontsize=7, alpha=0.6,
                    ha="center", va="top", zorder=7
                )

        # ── zone rectangles ──
        for z in zones:
            clr    = HIGH_CLR if z["type"] == "high" else LOW_CLR
            fa     = FILL_A_BRK if z["broken"] else FILL_A
            width  = z["right"] - z["left"]
            height = z["top"]   - z["bottom"]

            rect = mpatches.Rectangle(
                (z["left"], z["bottom"]),
                width, height,
                linewidth=0,
                facecolor=clr,
                alpha=fa,
                zorder=4,
            )
            ax.add_patch(rect)

            # top & bottom border lines
            ea = EDGE_A * (0.35 if z["broken"] else 1.0)
            ax.plot([z["left"], z["right"]], [z["top"],    z["top"]],
                    color=clr, linewidth=0.9, alpha=ea, zorder=5)
            ax.plot([z["left"], z["right"]], [z["bottom"], z["bottom"]],
                    color=clr, linewidth=0.9, alpha=ea, zorder=5)

        # ── swing diamond markers ──
        for s in swings:
            clr = HIGH_CLR if s["type"] == "high" else LOW_CLR
            ax.scatter(s["index"], s["price"],
                       color=clr, marker="D", s=70, zorder=8)
            ax.annotate(
                f"{s['price']:.1f}",
                xy=(s["index"], s["price"]),
                xytext=(0, 9 if s["type"] == "high" else -13),
                textcoords="offset points",
                ha="center", fontsize=7, color=clr,
            )

        # ── PDH / PDL horizontal lines ──
        pdh, pdl = previous_day_levels(ticker)
        if pdh is not None and pdl is not None:
            ax.axhline(pdh, color=PDH_CLR, linewidth=1.2,
                       linestyle="--", alpha=0.85, zorder=9)
            ax.text(last_x, pdh, f" PDH {pdh:.2f}",
                    color=PDH_CLR, fontsize=8, va="bottom",
                    ha="right", zorder=10)

            ax.axhline(pdl, color=PDL_CLR, linewidth=1.2,
                       linestyle="--", alpha=0.85, zorder=9)
            ax.text(last_x, pdl, f" PDL {pdl:.2f}",
                    color=PDL_CLR, fontsize=8, va="top",
                    ha="right", zorder=10)

        # ── X-axis: readable timestamps (same as FVG.py) ──
        n_ticks  = min(12, len(df))
        tick_pos = np.linspace(0, last_x, n_ticks, dtype=int)
        tick_lbl = [df.index[i].strftime("%d %b\n%H:%M") for i in tick_pos]
        ax.set_xticks(tick_pos)
        ax.set_xticklabels(tick_lbl, fontsize=7, color="#aaaaaa")
        ax.set_xlim(-1, last_x + 2)

        # ── legend ──
        legend_handles = [
            mpatches.Patch(color=HIGH_CLR, alpha=0.6, label="Swing High Zone"),
            mpatches.Patch(color=LOW_CLR,  alpha=0.6, label="Swing Low Zone"),
        ]
        if pdh is not None:
            legend_handles += [
                mpatches.Patch(color=PDH_CLR, alpha=0.85, label=f"PDH  {pdh:.2f}"),
                mpatches.Patch(color=PDL_CLR, alpha=0.85, label=f"PDL  {pdl:.2f}"),
            ]
        ax.legend(
            handles=legend_handles, fontsize=8,
            facecolor="#1e1e1e", edgecolor="#444444", labelcolor="#e0e0e0",
            loc="upper left"
        )

        # ── axes styling ──
        ax.tick_params(axis="y", colors="#aaaaaa", labelsize=8)
        ax.set_ylabel("Price", color="#aaaaaa", fontsize=9)
        ax.grid(True, alpha=0.12, color="#444444", linewidth=0.5)
        for spine in ax.spines.values():
            spine.set_edgecolor("#333333")

        plt.tight_layout()
        plt.show()
