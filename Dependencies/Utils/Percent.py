from dataclasses import dataclass
import os, sys

from Data_Manager import Download, download_daily_all, get_data

# =========================================================
# CANDLE ANATOMY RESULT
# =========================================================

@dataclass
class CandleBreakdown:
    body_pct:       float   # % of total range occupied by the body
    upper_wick_pct: float   # % of total range occupied by the upper wick
    lower_wick_pct: float   # % of total range occupied by the lower wick
    label:          str     # "Bullish" | "Bearish" | "Doji"

    def __repr__(self):
        return (
            f"CandleBreakdown("
            f"label={self.label}, "
            f"body={self.body_pct:.1f}%, "
            f"upper_wick={self.upper_wick_pct:.1f}%, "
            f"lower_wick={self.lower_wick_pct:.1f}%)"
        )


# =========================================================
# CORE FUNCTION
# =========================================================

def candle_breakdown(open_: float, high: float, low: float, close: float,
                     doji_threshold: float = 5.0,
                     wick_dominance: float = 51.0,
                     doji_wick_balance: float = 15.0) -> CandleBreakdown:
    """
    Break a single OHLC candle into body / upper-wick / lower-wick percentages
    and classify it as Bullish, Bearish, or Doji.

    Classification rules (evaluated in order)
    ------------------------------------------
    1. Doji   – body_pct is tiny AND both wicks are roughly equal:
                  body_pct  <=  doji_threshold          (default  5 %)
                  |upper_wick_pct − lower_wick_pct|  <=  doji_wick_balance  (default 15 %)
    2. Bearish – upper_wick_pct  >=  wick_dominance     (default 51 %)
                 upper wick dominates → rejection of highs → bearish pressure
    3. Bullish – lower_wick_pct  >=  wick_dominance     (default 51 %)
                 lower wick dominates → rejection of lows  → bullish pressure
    4. Fallback – body direction:  close >= open → Bullish, else Bearish

    Parameters
    ----------
    open_              : candle open price
    high               : candle high price
    low                : candle low price
    close              : candle close price
    doji_threshold     : max body % for a candle to qualify as Doji (default 5 %)
    wick_dominance     : min wick % that overrides body direction   (default 51 %)
    doji_wick_balance  : max allowed difference between the two wicks for Doji (default 15 %)

    Returns
    -------
    CandleBreakdown dataclass with:
        body_pct        – body size as % of total range
        upper_wick_pct  – upper wick as % of total range
        lower_wick_pct  – lower wick as % of total range
        label           – "Bullish" | "Bearish" | "Doji"

    All three percentages always sum to 100 %.
    A flat candle (high == low) returns 0 % everywhere and is labelled Doji.
    """
    total_range = high - low

    # ── Flat / zero-range candle guard ────────────────────────────
    if total_range == 0:
        return CandleBreakdown(
            body_pct=0.0,
            upper_wick_pct=0.0,
            lower_wick_pct=0.0,
            label="Doji"
        )

    body        = abs(close - open_)
    upper_wick  = high - max(open_, close)
    lower_wick  = min(open_, close) - low

    body_pct        = (body       / total_range) * 100
    upper_wick_pct  = (upper_wick / total_range) * 100
    lower_wick_pct  = (lower_wick / total_range) * 100

    # ── Classification ────────────────────────────────────────────
    if body_pct <= doji_threshold:
        # Small body → Doji
        label = "Doji"
    elif upper_wick_pct >= wick_dominance:
        # Upper wick ≥ 51 % of total range → bearish rejection at highs
        label = "Bearish"
    elif lower_wick_pct >= wick_dominance:
        # Lower wick ≥ 51 % of total range → bullish rejection at lows
        label = "Bullish"
    else:
        # Fallback: plain body direction
        label = "Bullish" if close >= open_ else "Bearish"

    return CandleBreakdown(
        body_pct=round(body_pct,       2),
        upper_wick_pct=round(upper_wick_pct, 2),
        lower_wick_pct=round(lower_wick_pct, 2),
        label=label
    )


# =========================================================
# VISUALISATION
# =========================================================

def plot_candle_breakdown(df: "pd.DataFrame", ticker: str = "",
                          max_candles: int = 60) -> None:
    """
    Plot a candlestick chart where every candle is annotated with its
    body / upper-wick / lower-wick percentages and Bullish/Bearish/Doji label.

    Parameters
    ----------
    df          : OHLC DataFrame with columns Open, High, Low, Close
                  and a DatetimeIndex (IST-aware, as returned by get_data).
    ticker      : Label used in the chart title.
    max_candles : Cap number of bars shown (most-recent N kept).
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    import numpy as np

    if df is None or df.empty:
        print("plot_candle_breakdown: dataframe is empty.")
        return

    # Keep the most-recent N candles so annotations stay readable
    plot_df = df.tail(max_candles).reset_index(drop=False)

    opens  = plot_df["Open"].to_numpy(dtype=float)
    highs  = plot_df["High"].to_numpy(dtype=float)
    lows   = plot_df["Low"].to_numpy(dtype=float)
    closes = plot_df["Close"].to_numpy(dtype=float)
    n      = len(plot_df)
    x_vals = range(n)

    # Pre-compute breakdown for every candle
    breakdowns = [candle_breakdown(opens[i], highs[i], lows[i], closes[i])
                  for i in x_vals]

    # ── Colours ───────────────────────────────────────────────────
    BULL_C = "#26a69a"
    BEAR_C = "#ef5350"
    DOJI_C = "#ffd54f"
    BG     = "#141414"
    FIG_BG = "#0f0f0f"
    GRID_C = "#2a2a2a"

    LABEL_COLORS = {"Bullish": BULL_C, "Bearish": BEAR_C, "Doji": DOJI_C}

    # ── Figure ────────────────────────────────────────────────────
    fig, (ax_candle, ax_bar) = plt.subplots(
        2, 1, figsize=(max(14, n * 0.35), 9),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True
    )
    fig.patch.set_facecolor(FIG_BG)
    for ax in (ax_candle, ax_bar):
        ax.set_facecolor(BG)
        ax.grid(True, color=GRID_C, linewidth=0.5, alpha=0.6)
        for spine in ax.spines.values():
            spine.set_edgecolor("#333333")

    title = f"{ticker}  —  Candle Breakdown" if ticker else "Candle Breakdown"
    fig.suptitle(title, fontsize=13, color="#e0e0e0", fontweight="bold")

    # ── Candlestick + annotations ─────────────────────────────────
    for i in x_vals:
        bd      = breakdowns[i]
        # candle colour driven purely by close vs open — NOT the label
        candle_color = BULL_C if closes[i] >= opens[i] else BEAR_C
        label_color  = LABEL_COLORS[bd.label]   # label text keeps its own colour
        body_lo = min(opens[i], closes[i])
        body_hi = max(opens[i], closes[i])
        body_h  = body_hi - body_lo or (highs[i] - lows[i]) * 0.001  # doji guard

        # Wick
        ax_candle.plot([i, i], [lows[i], highs[i]],
                       color=candle_color, linewidth=0.9, zorder=2)
        # Body
        ax_candle.add_patch(Rectangle(
            (i - 0.38, body_lo), 0.76, body_h,
            facecolor=candle_color, edgecolor=candle_color, linewidth=0.4,
            alpha=0.85, zorder=3
        ))

        # ── Per-candle annotations (only when candles are wide enough) ──
        if max_candles <= 40:
            mid_price = (highs[i] + lows[i]) / 2
            offset    = (highs[i] - lows[i]) * 0.08

            # Label above high — uses label colour
            ax_candle.text(
                i, highs[i] + offset,
                bd.label,
                color=label_color, fontsize=5.5, ha="center", va="bottom",
                fontweight="bold", zorder=5
            )
            # Body % inside / near body
            ax_candle.text(
                i, body_lo + body_h / 2,
                f"B:{bd.body_pct:.0f}%",
                color="#ffffff", fontsize=4.5, ha="center", va="center",
                zorder=5
            )
            # Upper wick % above body
            if bd.upper_wick_pct > 2:
                ax_candle.text(
                    i, body_hi + (highs[i] - body_hi) / 2,
                    f"U:{bd.upper_wick_pct:.0f}%",
                    color="#cccccc", fontsize=4.2, ha="center", va="center",
                    zorder=5
                )
            # Lower wick % below body
            if bd.lower_wick_pct > 2:
                ax_candle.text(
                    i, lows[i] + (body_lo - lows[i]) / 2,
                    f"L:{bd.lower_wick_pct:.0f}%",
                    color="#cccccc", fontsize=4.2, ha="center", va="center",
                    zorder=5
                )

    ax_candle.set_ylabel("Price", color="#aaaaaa", fontsize=9)
    ax_candle.tick_params(axis="y", colors="#aaaaaa", labelsize=7)
    ax_candle.set_xlim(-1, n)

    # ── Stacked bar chart: body / upper-wick / lower-wick % ───────
    body_pcts  = [bd.body_pct        for bd in breakdowns]
    upper_pcts = [bd.upper_wick_pct  for bd in breakdowns]
    lower_pcts = [bd.lower_wick_pct  for bd in breakdowns]
    bar_colors = [LABEL_COLORS[bd.label] for bd in breakdowns]
    xs = list(x_vals)
    ax_bar.bar(xs, body_pcts,  color=bar_colors,  alpha=0.85, label="Body",        zorder=3)
    ax_bar.bar(xs, upper_pcts, bottom=body_pcts,
               color="#90caf9", alpha=0.65, label="Upper Wick", zorder=3)
    ax_bar.bar(xs, lower_pcts,
               bottom=[b + u for b, u in zip(body_pcts, upper_pcts)],
               color="#ce93d8", alpha=0.65, label="Lower Wick", zorder=3)

    ax_bar.axhline(100, color="#555555", linewidth=0.6, linestyle="--")
    ax_bar.set_ylabel("% of Range", color="#aaaaaa", fontsize=8)
    ax_bar.tick_params(axis="y", colors="#aaaaaa", labelsize=7)
    ax_bar.set_ylim(0, 115)
    ax_bar.legend(fontsize=7, facecolor="#1e1e1e",
                  edgecolor="#444444", labelcolor="#e0e0e0",
                  loc="upper right", ncol=3)

    # ── X-axis timestamps ─────────────────────────────────────────
    time_col = plot_df.columns[0]          # the reset_index puts the old index first
    n_ticks  = min(12, n)
    tick_pos = [int(p) for p in __import__("numpy").linspace(0, n - 1, n_ticks)]
    tick_lbl = [plot_df[time_col].iloc[i].strftime("%d %b\n%H:%M")
                for i in tick_pos]
    ax_bar.set_xticks(tick_pos)
    ax_bar.set_xticklabels(tick_lbl, fontsize=6.5, color="#aaaaaa")

    plt.tight_layout()
    plt.show()


def percent(ticker: str, interval: str = "15m") -> "CandleBreakdown | None":
    """
    Fetch the latest closed candle for *ticker* at *interval* and return
    its CandleBreakdown. Returns None if data is unavailable.
    """
    df = get_data(ticker, interval)
    if df is None or df.empty:
        return None

    row = df.iloc[-1]
    return candle_breakdown(row["Open"], row["High"], row["Low"], row["Close"])

# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    import os, sys

    from Data_Manager import Download, download_daily_all, get_data

    tickers = ["SHAREINDIA.NS"]
    print(f"Downloading data for {tickers} ...")
    Download(tickers, "20d")

    for ticker in tickers:
        df = get_data(ticker, "15m")
        if df is None or df.empty:
            print(f"{ticker} — no data.")
            continue

        # ── Console table ──────────────────────────────────────────
        # print(f"\n{'Time':<22} {'Label':<10} {'Body%':>7} {'Upper%':>8} {'Lower%':>8}")
        # print("-" * 60)
        for ts, row in df.tail(20).iterrows():
            bd = candle_breakdown(row["Open"], row["High"], row["Low"], row["Close"])
            # print(
            #     f"{str(ts):<1} {bd.label:<1} "
            #     # f"{bd.body_pct:>7.1f} "
            #     # f"{bd.upper_wick_pct:>8.1f} "
            #     # f"{bd.lower_wick_pct:>8.1f}"
            # )

        # ── Chart ──────────────────────────────────────────────────
        plot_candle_breakdown(df, ticker=ticker, max_candles=40)
