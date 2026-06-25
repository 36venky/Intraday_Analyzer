import os
import logging

from Data_Manager import *


# =========================================================
# PREVIOUS DAY LEVELS
# =========================================================

def previous_day_levels(ticker):
    """
    Returns (prev_high, prev_low) for the most recent FULLY CLOSED trading day.

    Strategy:
      - Pull the raw 1d dataframe directly from MARKET_DATA (bypassing
        get_data's candle-close guard, which can mis-strip the last row).
      - The yfinance 1d series only contains COMPLETED daily candles;
        a partial today candle never appears in period="1y" downloads.
      - We compare each candle's date against today's IST date and take the
        last candle whose IST date is strictly BEFORE today.

    Why IST: yfinance 1d timestamps are UTC midnight.  At 09:30 IST the UTC
    date is still yesterday, so a naive date comparison would incorrectly
    keep today's partial candle.  Converting to IST first fixes this.
    """
    from Data_Manager.data import MARKET_DATA
    import pandas as pd

    raw = MARKET_DATA.get(ticker, {}).get("1d")

    if raw is None or raw.empty:
        logging.warning(f"{ticker} daily data unavailable or insufficient.")
        return None, None

    # Convert index to IST so date comparisons align with the Indian
    # trading calendar regardless of what timezone yfinance used.
    IST = "Asia/Kolkata"
    try:
        if raw.index.tz is None:
            idx_ist = raw.index.tz_localize("UTC").tz_convert(IST)
        else:
            idx_ist = raw.index.tz_convert(IST)
        today_ist = pd.Timestamp.now(tz=IST).date()
    except Exception:
        idx_ist   = raw.index
        today_ist = pd.Timestamp.now().date()

    # Keep only candles strictly before today (IST)
    prev_df = raw[idx_ist.date < today_ist]

    if prev_df.empty:
        logging.warning(f"{ticker} 1d not available.")
        return None, None

    prev      = prev_df.iloc[-1]          # last completed trading day
    prev_high = float(prev["High"])
    prev_low  = float(prev["Low"])

    logging.info(f"{ticker} Prev High: {prev_high}, Prev Low: {prev_low}")
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
      - Bottom = swing candle Low
      - Left   = swing candle bar index
      - Right  = first bar (from swing+1) where close > top  (breakout above)
                 If never broken → extends to last bar

    SWING LOW zone:
      - Top    = swing candle High
      - Bottom = swing candle Low
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
    closes = df["Close"].values
    highs  = df["High"].values
    lows   = df["Low"].values
    n      = len(df)

    zones = []

    for s in swings:
        idx    = s["index"]
        top    = float(highs[idx])
        bottom = float(lows[idx])
        right  = n - 1
        broken = False

        if s["type"] == "high":
            for j in range(idx + 1, n):
                if closes[j] > top:
                    right  = j
                    broken = True
                    break
        else:  # low
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
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from Data_Manager import Download

    tickers = ["SALZERELEC.NS"]
    Download(tickers,"20d")
    download_daily_all(tickers)

    for ticker in tickers:

        df = get_data(ticker, "15m")
        if df is None or df.empty:
            print(f"{ticker} — no data.")
            continue

        swings = get_confirmed_swings(df, window=3, significance=0.005, confirm_pct=0.01)
        zones  = build_swing_zones(df, swings)
        closes = df["Close"].values

        # ── colours ──
        HIGH_CLR   = "#ef5350"   # red   — swing high zone
        LOW_CLR    = "#26a69a"   # teal  — swing low zone
        FILL_A     = 0.18        # fill alpha for active zones
        FILL_A_BRK = 0.07        # fill alpha for broken zones
        EDGE_A     = 0.75

        fig, ax = plt.subplots(figsize=(15, 7))
        fig.patch.set_facecolor("#0f0f0f")
        ax.set_facecolor("#0f0f0f")
        fig.suptitle(
            f"{ticker}  —  Swing High / Low Zones",
            fontsize=13, color="white", fontweight="bold"
        )

        # ── price line ──
        ax.plot(closes, color="#aaaaaa", linewidth=0.9, zorder=1)

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
                zorder=2,
            )
            ax.add_patch(rect)

            # top & bottom border lines
            ea = EDGE_A * (0.35 if z["broken"] else 1.0)
            ax.plot([z["left"], z["right"]], [z["top"],    z["top"]],
                    color=clr, linewidth=0.9, alpha=ea, zorder=3)
            ax.plot([z["left"], z["right"]], [z["bottom"], z["bottom"]],
                    color=clr, linewidth=0.9, alpha=ea, zorder=3)

        # ── swing diamond markers ──
        for s in swings:
            clr = HIGH_CLR if s["type"] == "high" else LOW_CLR
            ax.scatter(s["index"], s["price"],
                       color=clr, marker="D", s=70, zorder=4)
            ax.annotate(
                f"{s['price']:.1f}",
                xy=(s["index"], s["price"]),
                xytext=(0, 9 if s["type"] == "high" else -13),
                textcoords="offset points",
                ha="center", fontsize=7, color=clr,
            )

        # ── PDH / PDL horizontal lines ──
        PDH_CLR = "#ffb74d"   # amber  — previous day high
        PDL_CLR = "#81d4fa"   # sky    — previous day low

        pdh, pdl = previous_day_levels(ticker)
        if pdh is not None and pdl is not None:
            n_bars = len(closes)

            ax.axhline(pdh, color=PDH_CLR, linewidth=1.2,
                       linestyle="--", alpha=0.85, zorder=5)
            ax.text(n_bars - 1, pdh, f" PDH {pdh:.2f}",
                    color=PDH_CLR, fontsize=8, va="bottom",
                    ha="right", zorder=6)

            ax.axhline(pdl, color=PDL_CLR, linewidth=1.2,
                       linestyle="--", alpha=0.85, zorder=5)
            ax.text(n_bars - 1, pdl, f" PDL {pdl:.2f}",
                    color=PDL_CLR, fontsize=8, va="top",
                    ha="right", zorder=6)

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
        ax.legend(handles=legend_handles,
                  fontsize=8, facecolor="#1e1e1e",
                  edgecolor="#444444", labelcolor="white")

        # ── axes styling ──
        ax.set_xlabel("Bar Index", color="white", fontsize=9)
        ax.set_ylabel("Price",     color="white", fontsize=9)
        ax.tick_params(colors="white")
        for spine in ax.spines.values():
            spine.set_color("#444444")
        ax.grid(True, alpha=0.12, color="#444444")

        plt.tight_layout()
        plt.show()
