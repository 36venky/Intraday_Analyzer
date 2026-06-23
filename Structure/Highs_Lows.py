import os
import sys
import logging
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Data_Manager import *


# =========================================================
# PREVIOUS DAY LEVELS
# =========================================================

def previous_day_levels(ticker):
    df = get_data(ticker, "1d")

    if df is None or len(df) < 2:
        logging.warning(f"{ticker} daily data unavailable or insufficient.")
        return None, None

    prev       = df.iloc[-2]
    prev_high  = prev['High']
    prev_low   = prev['Low']

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
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from Data_Manager import Download

    tickers = ["PPLPHARMA.NS"]
    Download(tickers)
    download_daily_all(tickers)

    for ticker in tickers:

        prev_high, prev_low = previous_day_levels(ticker)
        if prev_high:
            print(f"{ticker}  Prev High: {prev_high:.2f}  Prev Low: {prev_low:.2f}")

        df = get_data(ticker, "15m")
        #print(df.tail(2))
        if df is None or df.empty:
            print(f"{ticker} — no data.")
            continue

        swings  = get_confirmed_swings(df, window=3, significance=0.005, confirm_pct=0.01)
        # for item in swings:
        #     print(f"{item['index']},{item['price']},{item['type']}\n")
        closes  = df["Close"].values

        fig, ax = plt.subplots(figsize=(14, 6))
        fig.patch.set_facecolor("#0f0f0f")
        ax.set_facecolor("#0f0f0f")
        fig.suptitle(f"{ticker} — Confirmed Swing Structure (>1% follow-through)",
                     fontsize=13, color="white")

        ax.plot(closes, color="#aaaaaa", linewidth=1, zorder=1, label="Close")

        if prev_high:
            ax.axhline(prev_high, color="#f0a500", linewidth=1,
                       linestyle="--", label=f"Prev High {prev_high:.2f}")
            ax.axhline(prev_low,  color="#7b61ff", linewidth=1,
                       linestyle="--", label=f"Prev Low {prev_low:.2f}")

        sx = [s["index"] for s in swings]
        sy = [s["price"] for s in swings]
        ax.plot(sx, sy, color="#555555", linewidth=0.9, linestyle="--", zorder=2)

        for s in swings:
            color = "#26a69a" if s["type"] == "high" else "#ef5350"
            ax.scatter(s["index"], s["price"], color=color, marker="D", s=90, zorder=3)
            ax.annotate(f"{s['price']:.1f}", xy=(s["index"], s["price"]),
                        xytext=(0, 10 if s["type"] == "high" else -14),
                        textcoords="offset points", ha="center", fontsize=7, color=color)

        ax.legend(handles=[
            mpatches.Patch(color="#26a69a", label="Confirmed High ◆"),
            mpatches.Patch(color="#ef5350", label="Confirmed Low ◆"),
        ] + ax.get_legend_handles_labels()[0][-2:], fontsize=8,
          facecolor="#1e1e1e", edgecolor="#444444", labelcolor="white")

        ax.set_xlabel("Bar Index", color="white")
        ax.set_ylabel("Price", color="white")
        ax.tick_params(colors="white")
        ax.spines["bottom"].set_color("#444444")
        ax.spines["top"].set_color("#444444")
        ax.spines["left"].set_color("#444444")
        ax.spines["right"].set_color("#444444")
        ax.grid(True, alpha=0.15, color="#444444")
        plt.tight_layout()
        plt.show()
