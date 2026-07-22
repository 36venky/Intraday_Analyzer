import logging
import numpy as np
import pandas as pd

from Data_Manager import *

# =========================================================
# CONSTANTS
# =========================================================

_IST          = "Asia/Kolkata"
_MARKET_OPEN  = (9, 30)   # HH, MM  — 09:30 IST
_ZONE_LOOKBACK = 7        # candles to search for the 50%-cross candle


# =========================================================
# INTERNAL HELPERS
# =========================================================

def _to_ist(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Normalise any DatetimeIndex to IST, handling both tz-naive and tz-aware inputs."""
    if index.tz is None:
        return index.tz_localize("UTC").tz_convert(_IST)
    return index.tz_convert(_IST)


def _now_ist() -> pd.Timestamp:
    return pd.Timestamp.now(tz=_IST)


def _is_live_today(intraday: pd.DataFrame | None, today) -> bool:
    """
    Return True if `intraday` contains at least one candle dated today (IST).
    Gracefully returns False on any error or missing data.
    """
    if intraday is None or intraday.empty:
        return False
    try:
        return today in _to_ist(intraday.index).date
    except Exception:
        return False


def _ref_day_index(prev_df: pd.DataFrame, ticker: str, live_today: bool) -> int | None:
    """
    Resolve which completed-day row to use as the reference.

    Rules:
      - live_today=True  → iloc[-1]  (yesterday)
      - live_today=False → iloc[-2]  (day-before-yesterday); needs ≥2 rows
    """
    if live_today:
        return -1
    if len(prev_df) < 2:
        logging.warning(f"{ticker}: not enough daily history for pre-market PDH/PDL.")
        return None
    return -2


# =========================================================
# PREVIOUS DAY LEVELS
# =========================================================

def previous_day_levels(ticker: str) -> tuple[float | None, float | None]:
    """
    Return (PDH, PDL) for the correct reference trading day.

    Reference-day selection (IST):
      - After 09:30 AND live intraday candle present for today
            → yesterday  (iloc[-1] of completed days)
      - Before 09:30 OR no live intraday data yet
            → day-before-yesterday (iloc[-2] of completed days)

    'Completed days' = all 1d candles whose IST date < today.
    """
    from Data_Manager.data import MARKET_DATA

    raw = MARKET_DATA.get(ticker, {}).get("1d")
    if raw is None or raw.empty:
        logging.warning(f"{ticker}: daily data unavailable.")
        return None, None

    now        = _now_ist()
    today      = now.date()
    market_open = now.replace(hour=_MARKET_OPEN[0], minute=_MARKET_OPEN[1],
                               second=0, microsecond=0)

    # All fully-closed daily candles
    try:
        daily_ist_dates = _to_ist(raw.index).date
    except Exception:
        daily_ist_dates = raw.index.date

    prev_df = raw[daily_ist_dates < today]
    if prev_df.empty:
        logging.warning(f"{ticker}: no completed daily candles.")
        return None, None

    # Live-data probe: prefer 15m, fall back to 5m / 1m
    intraday = (
        MARKET_DATA.get(ticker, {}).get("15m")
    )
    live_today = (now >= market_open) and _is_live_today(intraday, today)

    iloc_idx = _ref_day_index(prev_df, ticker, live_today)
    if iloc_idx is None:
        return None, None

    ref       = prev_df.iloc[iloc_idx]
    prev_high = float(ref["High"])
    prev_low  = float(ref["Low"])

    logging.info(
        f"{ticker}: PDH/PDL ref={ref.name.date() if hasattr(ref.name, 'date') else ref.name} "
        f"| PDH={prev_high:.2f}  PDL={prev_low:.2f}"
    )
    return prev_high, prev_low


# =========================================================
# RAW SWING DETECTION  (vectorised)
# =========================================================

def swing_points(
    highs: np.ndarray,
    lows:  np.ndarray,
    window: int = 3,
) -> tuple[list[int], list[int]]:
    """
    Detect local swing high/low indices using a vectorised rolling-window approach.

    Returns (swing_lows_idx, swing_highs_idx).
    """
    n = len(highs)
    if n < 2 * window + 1:
        return [], []

    # rolling max of highs and rolling min of lows — O(n) with pandas
    h_series      = pd.Series(highs)
    l_series      = pd.Series(lows)
    roll_max_high = h_series.rolling(2 * window + 1, center=True).max()
    roll_min_low  = l_series.rolling(2 * window + 1, center=True).min()

    valid = np.arange(window, n - window)
    swing_highs = valid[highs[valid] == roll_max_high.values[valid]].tolist()
    swing_lows  = valid[lows[valid]  == roll_min_low.values[valid]].tolist()

    return swing_lows, swing_highs


# =========================================================
# HELPERS
# =========================================================

def _keep_extreme(result: list[dict], p: dict) -> None:
    """Replace last point in-place if same type and `p` is more extreme."""
    last = result[-1]
    if p["type"] != last["type"]:
        result.append(p)
        return
    if p["type"] == "high" and p["price"] > last["price"]:
        result[-1] = p
    elif p["type"] == "low" and p["price"] < last["price"]:
        result[-1] = p


def _tag_points(
    highs:      np.ndarray,
    lows:       np.ndarray,
    highs_idx:  list[int],
    lows_idx:   list[int],
) -> list[dict]:
    """Tag raw indices and return a single list sorted by bar index."""
    points = [{"index": i, "price": float(lows[i]),  "type": "low"}  for i in lows_idx]
    points += [{"index": i, "price": float(highs[i]), "type": "high"} for i in highs_idx]
    points.sort(key=lambda p: p["index"])
    return points


# =========================================================
# SIGNIFICANT SWINGS  (0.5 % consecutive dedup)
# =========================================================

def get_significant_swings(
    df:           pd.DataFrame,
    window:       int   = 3,
    significance: float = 0.005,
) -> list[dict]:
    """
    Return swing points after merging consecutive same-type clusters:
      - price diff > significance  → keep both
      - price diff ≤ significance  → keep only the extreme
    """
    highs = df["High"].to_numpy()
    lows  = df["Low"].to_numpy()

    raw_lows_idx, raw_highs_idx = swing_points(highs, lows, window)
    points = _tag_points(highs, lows, raw_highs_idx, raw_lows_idx)

    if not points:
        return []

    result: list[dict] = [points[0]]

    for curr in points[1:]:
        last = result[-1]
        if curr["type"] != last["type"]:
            result.append(curr)
            continue
        # same type — check significance
        diff = abs(curr["price"] - last["price"]) / last["price"]
        if diff > significance:
            result.append(curr)
        else:
            _keep_extreme(result, curr)

    return result


# =========================================================
# CONFIRMED SWINGS  (1 % follow-through + extreme dedup)
# =========================================================

def get_confirmed_swings(
    df:           pd.DataFrame,
    window:       int   = 3,
    significance: float = 0.005,
    confirm_pct:  float = 0.01,
) -> list[dict]:
    """
    Pipeline:
      1. get_significant_swings  — 0.5 % consecutive dedup
      2. O(n) forward scan: confirm each point by the *immediately following*
         opposing swing moving > confirm_pct
      3. Dedup remaining consecutive same-type → keep extreme

    Returns list of { 'index', 'price', 'type' }.
    """
    sig = get_significant_swings(df, window=window, significance=significance)
    if not sig:
        return []

    # ── Step 2: O(n) confirmation pass ──
    # For each point find its first opposing neighbour in one forward pass.
    confirmed: list[dict] = []
    n = len(sig)

    for i in range(n - 1):
        point = sig[i]
        # Walk forward to find the nearest point of the opposite type
        for j in range(i + 1, n):
            nxt = sig[j]
            if nxt["type"] == point["type"]:
                continue
            diff = abs(nxt["price"] - point["price"]) / point["price"]
            if point["type"] == "high" and nxt["price"] < point["price"] and diff > confirm_pct:
                confirmed.append(point)
            elif point["type"] == "low" and nxt["price"] > point["price"] and diff > confirm_pct:
                confirmed.append(point)
            break   # only first opposing neighbour counts

    # ── Step 3: dedup consecutive same-type ──
    result: list[dict] = []
    for p in confirmed:
        if not result:
            result.append(p)
        else:
            _keep_extreme(result, p)

    return result


# =========================================================
# SWING ZONES  (rectangle from swing candle → breakout)
# =========================================================

def build_swing_zones(df: pd.DataFrame, swings: list[dict]) -> list[dict]:
    """
    For each confirmed swing build a rectangle zone.

    SWING HIGH zone:
      top    = swing candle High
      bottom = close of the first bearish candle (within ZONE_LOOKBACK bars)
               whose close is below the 50% midpoint; fallback = swing close
      right  = first bar (from swing+1) where close > top  (breakout above)

    SWING LOW zone:
      bottom = swing candle Low
      top    = close of the first bullish candle (within ZONE_LOOKBACK bars)
               whose close is above the 50% midpoint; fallback = swing close
      right  = first bar (from swing+1) where close < bottom (breakout below)

    Breakout is confirmed by a candle CLOSE, not just a wick.

    Returns list of dicts:
        { 'type', 'left', 'right', 'top', 'bottom', 'broken' }
    """
    if not swings:
        return []

    opens  = df["Open"].values
    closes = df["Close"].values
    highs  = df["High"].values
    lows   = df["Low"].values
    n      = len(df)

    zones: list[dict] = []

    for s in swings:
        idx      = s["index"]
        sw_high  = float(highs[idx])
        sw_low   = float(lows[idx])
        midpoint = (sw_high + sw_low) * 0.5
        right    = n - 1
        broken   = False

        if s["type"] == "high":
            top    = sw_high
            bottom = float(closes[idx])   # fallback

            end = min(idx + 1 + _ZONE_LOOKBACK, n)
            for j in range(idx + 1, end):
                if closes[j] < opens[j] and closes[j] < midpoint:
                    bottom = float(closes[j])
                    break

            # Vectorised breakout search
            future_closes = closes[idx + 1:]
            brk = np.argmax(future_closes > top)   # 0 if not found OR first hit
            if brk > 0 or (len(future_closes) > 0 and future_closes[0] > top):
                right  = idx + 1 + int(brk)
                broken = True

        else:   # low
            bottom = sw_low
            top    = float(closes[idx])   # fallback

            end = min(idx + 1 + _ZONE_LOOKBACK, n)
            for j in range(idx + 1, end):
                if closes[j] > opens[j] and closes[j] > midpoint:
                    top = float(closes[j])
                    break

            future_closes = closes[idx + 1:]
            brk = np.argmax(future_closes < bottom)
            if brk > 0 or (len(future_closes) > 0 and future_closes[0] < bottom):
                right  = idx + 1 + int(brk)
                broken = True

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
    from matplotlib.collections import LineCollection, PatchCollection
    from matplotlib.patches import Rectangle
    from Data_Manager import Download

    tickers = ["BLUESTONE.NS"]
    Download(tickers, "10d")
    download_daily_all(tickers)

    # ── colour palette ──
    BULL_C     = "#26a69a"
    BEAR_C     = "#ef5350"
    HIGH_CLR   = "#ef5350"
    LOW_CLR    = "#26a69a"
    FILL_A     = 0.18
    FILL_A_BRK = 0.07
    EDGE_A     = 0.75
    PDH_CLR    = "#ffb74d"
    PDL_CLR    = "#81d4fa"
    VLINE_CLR  = "#ffffff"

    for ticker in tickers:
        df = get_data(ticker, "4h")
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

        fig, ax = plt.subplots(figsize=(16, 7))
        fig.patch.set_facecolor("#0f0f0f")
        ax.set_facecolor("#141414")
        fig.suptitle(
            f"{ticker}  —  Swing High / Low Zones",
            fontsize=13, color="#e0e0e0", fontweight="bold",
        )

        # ── vectorised candlestick rendering ──
        bull_mask = closes >= opens
        body_lo   = np.where(bull_mask, opens,  closes)
        body_hi   = np.where(bull_mask, closes, opens)
        body_h    = np.where(body_hi - body_lo > 0,
                             body_hi - body_lo,
                             (highs - lows) * 0.001)   # doji guard

        bull_idx = x_vals[bull_mask]
        bear_idx = x_vals[~bull_mask]

        # Wicks via LineCollection (one draw call per colour)
        wick_segs = [[(i, lows[i]), (i, highs[i])] for i in x_vals]
        wick_cols = [BULL_C if bull_mask[i] else BEAR_C for i in x_vals]
        ax.add_collection(LineCollection(wick_segs, colors=wick_cols, linewidths=0.8, zorder=2))

        # Bodies via PatchCollection
        bull_patches = [Rectangle((i - 0.35, body_lo[i]), 0.70, body_h[i]) for i in bull_idx]
        bear_patches = [Rectangle((i - 0.35, body_lo[i]), 0.70, body_h[i]) for i in bear_idx]

        if bull_patches:
            ax.add_collection(PatchCollection(bull_patches, facecolor=BULL_C,
                                              edgecolor=BULL_C, linewidth=0.4, zorder=3))
        if bear_patches:
            ax.add_collection(PatchCollection(bear_patches, facecolor=BEAR_C,
                                              edgecolor=BEAR_C, linewidth=0.4, zorder=3))

        # ── reference-day vertical boundary lines ──
        now_ist   = _now_ist()
        today_ist = now_ist.date()
        market_open_ts = now_ist.replace(
            hour=_MARKET_OPEN[0], minute=_MARKET_OPEN[1], second=0, microsecond=0
        )

        try:
            bar_ist_dates = _to_ist(df.index).date
        except Exception:
            bar_ist_dates = df.index.date

        live_today = (now_ist >= market_open_ts) and (today_ist in bar_ist_dates)
        prev_dates = sorted({d for d in bar_ist_dates if d < today_ist})

        if prev_dates:
            if live_today:
                ref_day = prev_dates[-1]
            else:
                ref_day = prev_dates[-2] if len(prev_dates) >= 2 else prev_dates[-1]

            ref_mask    = bar_ist_dates == ref_day
            ref_indices = np.where(ref_mask)[0]
            if len(ref_indices) > 0:
                pd_start = int(ref_indices[0])
                pd_end   = int(ref_indices[-1])
                ax.axvline(pd_start - 0.5, color=VLINE_CLR, lw=1.0,
                           ls="--", alpha=0.55, zorder=6)
                ax.axvline(pd_end   + 0.5, color=VLINE_CLR, lw=1.0,
                           ls="--", alpha=0.55, zorder=6)
                ax.text(
                    (pd_start + pd_end) / 2, highs.max(),
                    f"Prev Day  {ref_day.strftime('%d %b')}",
                    color=VLINE_CLR, fontsize=7, alpha=0.6,
                    ha="center", va="top", zorder=7,
                )

        # ── zone rectangles ──
        for z in zones:
            clr   = HIGH_CLR if z["type"] == "high" else LOW_CLR
            fa    = FILL_A_BRK if z["broken"] else FILL_A
            ea    = EDGE_A * (0.35 if z["broken"] else 1.0)
            width = z["right"] - z["left"]
            height = z["top"] - z["bottom"]

            ax.add_patch(mpatches.Rectangle(
                (z["left"], z["bottom"]), width, height,
                linewidth=0, facecolor=clr, alpha=fa, zorder=4,
            ))
            ax.plot([z["left"], z["right"]], [z["top"],    z["top"]],
                    color=clr, lw=0.9, alpha=ea, zorder=5)
            ax.plot([z["left"], z["right"]], [z["bottom"], z["bottom"]],
                    color=clr, lw=0.9, alpha=ea, zorder=5)

        # ── swing diamond markers (vectorised scatter) ──
        if swings:
            hi_swings  = [s for s in swings if s["type"] == "high"]
            lo_swings  = [s for s in swings if s["type"] == "low"]
            if hi_swings:
                hx = [s["index"] for s in hi_swings]
                hy = [s["price"] for s in hi_swings]
                ax.scatter(hx, hy, color=HIGH_CLR, marker="D", s=70, zorder=8)
                for x, y in zip(hx, hy):
                    ax.annotate(f"{y:.1f}", xy=(x, y),
                                xytext=(0, 9), textcoords="offset points",
                                ha="center", fontsize=7, color=HIGH_CLR)
            if lo_swings:
                lx = [s["index"] for s in lo_swings]
                ly = [s["price"] for s in lo_swings]
                ax.scatter(lx, ly, color=LOW_CLR, marker="D", s=70, zorder=8)
                for x, y in zip(lx, ly):
                    ax.annotate(f"{y:.1f}", xy=(x, y),
                                xytext=(0, -13), textcoords="offset points",
                                ha="center", fontsize=7, color=LOW_CLR)

        # ── PDH / PDL horizontal lines ──
        pdh, pdl = previous_day_levels(ticker)
        if pdh is not None and pdl is not None:
            ax.axhline(pdh, color=PDH_CLR, lw=1.2, ls="--", alpha=0.85, zorder=9)
            ax.text(last_x, pdh, f" PDH {pdh:.2f}",
                    color=PDH_CLR, fontsize=8, va="bottom", ha="right", zorder=10)
            ax.axhline(pdl, color=PDL_CLR, lw=1.2, ls="--", alpha=0.85, zorder=9)
            ax.text(last_x, pdl, f" PDL {pdl:.2f}",
                    color=PDL_CLR, fontsize=8, va="top", ha="right", zorder=10)

        # ── X-axis timestamps ──
        n_ticks  = min(12, len(df))
        tick_pos = np.linspace(0, last_x, n_ticks, dtype=int)
        tick_lbl = [df.index[i].strftime("%d %b\n%H:%M") for i in tick_pos]
        ax.set_xticks(tick_pos)
        ax.set_xticklabels(tick_lbl, fontsize=7, color="#aaaaaa")
        ax.set_xlim(-1, last_x + 2)
        ax.autoscale_view()

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
        ax.legend(handles=legend_handles, fontsize=8,
                  facecolor="#1e1e1e", edgecolor="#444444",
                  labelcolor="#e0e0e0", loc="upper left")

        # ── axes styling ──
        ax.tick_params(axis="y", colors="#aaaaaa", labelsize=8)
        ax.set_ylabel("Price", color="#aaaaaa", fontsize=9)
        ax.grid(True, alpha=0.12, color="#444444", linewidth=0.5)
        for spine in ax.spines.values():
            spine.set_edgecolor("#333333")

        plt.tight_layout()
        plt.show()