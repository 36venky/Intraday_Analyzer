import os
import logging
import numpy as np
import pandas as pd

from Data_Manager import get_data


# =========================================================
# FAIR VALUE GAP DETECTION
# =========================================================

def detect_fvg(df: pd.DataFrame, mitigated: bool = True) -> pd.DataFrame:
    """
    Detect Fair Value Gaps (FVG) from an OHLC dataframe using
    fully vectorized numpy/pandas operations.

    Rules
    -----
    Bullish FVG : Low[i]  > High[i-2]   (gap between candle 1 high and candle 3 low)
    Bearish FVG : High[i] < Low[i-2]    (gap between candle 1 low  and candle 3 high)

    Parameters
    ----------
    df          : DataFrame with columns Open, High, Low, Close and a DatetimeIndex.
    mitigated   : If True, add a boolean column `Mitigated` and the timestamp
                  `Mitigated_At` when price closed inside the gap.

    Returns
    -------
    DataFrame with columns:
        Timestamp   – bar index where the FVG formed (candle 3)
        Direction   – "Bullish" | "Bearish"
        Top         – upper boundary of the gap
        Bottom      – lower boundary of the gap
        Mitigated   – True if fully filled by later price action  (only if mitigated=True)
        Mitigated_At– first timestamp the gap was fully closed    (only if mitigated=True)
    """
    if df is None or len(df) < 3:
        logging.warning("FVG: dataframe too short (need ≥ 3 bars).")
        return pd.DataFrame()

    high  = df["High"].to_numpy(dtype=np.float64)
    low   = df["Low"].to_numpy(dtype=np.float64)
    close = df["Close"].to_numpy(dtype=np.float64)
    idx   = df.index

    # ── Vectorised detection (shift by 2) ──────────────────────────
    h1 = high[:-2]   # High of candle i-2
    l1 = low[:-2]    # Low  of candle i-2
    h3 = high[2:]    # High of candle i   (candle 3)
    l3 = low[2:]     # Low  of candle i

    bull_mask = l3 > h1          # gap above candle-1 high
    bear_mask = h3 < l1          # gap below candle-1 low

    records = []

    for mask, direction in ((bull_mask, "Bullish"), (bear_mask, "Bearish")):
        positions = np.where(mask)[0] + 2          # shift back to original index

        for pos in positions:
            if direction == "Bullish":
                top    = float(low[pos])            # candle 3 low
                bottom = float(high[pos - 2])       # candle 1 high
            else:
                top    = float(low[pos - 2])        # candle 1 low
                bottom = float(high[pos])           # candle 3 high

            records.append({
                "Timestamp": idx[pos],
                "Direction": direction,
                "Top"      : top,
                "Bottom"   : bottom,
            })

    if not records:
        logging.info("FVG: no gaps detected.")
        return pd.DataFrame()

    fvg_df = (
        pd.DataFrame(records)
        .sort_values("Timestamp")
        .reset_index(drop=True)
    )

    # ── Mitigation check ───────────────────────────────────────────
    if mitigated:
        fvg_df = _check_mitigation(fvg_df, df)

    return fvg_df


# =========================================================
# MITIGATION HELPER
# =========================================================

def _check_mitigation(fvg_df: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
    """
    For each FVG, scan subsequent candles to find the first bar
    where price fully closes inside the gap (i.e. the gap is filled).

    Mitigation condition
    --------------------
    Bullish : a later Close ≤ Bottom  (price retraced into the up-gap)
    Bearish : a later Close ≥ Top     (price rallied into the down-gap)

    Vectorised per FVG using searchsorted for the start index,
    then numpy argmax on a boolean slice.
    """
    close      = price_df["Close"].to_numpy(dtype=np.float64)
    timestamps = price_df.index.to_numpy()          # numpy datetime64

    mit_flag = np.zeros(len(fvg_df), dtype=bool)
    #  create the series with a tz-aware dtype matching the price_df index
    _tz      = price_df.index.tz
    _dtype   = pd.DatetimeTZDtype(tz=_tz) if _tz is not None else "datetime64[ns]"
    mit_at   = pd.Series(pd.NaT, index=fvg_df.index, dtype=_dtype)

    ts_numeric = price_df.index.view(np.int64)      # for searchsorted

    for i, row in fvg_df.iterrows():
        # first bar *after* the FVG formation
        fvg_ts   = row["Timestamp"]
        start    = ts_numeric.searchsorted(
            np.int64(fvg_ts.value), side="right"
        )

        if start >= len(close):
            continue

        future_close = close[start:]

        if row["Direction"] == "Bullish":
            filled = future_close <= row["Bottom"]
        else:
            filled = future_close >= row["Top"]

        if filled.any():
            hit_offset       = int(np.argmax(filled))
            mit_flag[i]      = True
            mit_at[i]        = timestamps[start + hit_offset]

    fvg_df["Mitigated"]    = mit_flag
    fvg_df["Mitigated_At"] = pd.to_datetime(mit_at)
    return fvg_df


# =========================================================
# ACTIVE FVGs  (convenience filter)
# =========================================================

def active_fvg(fvg_df: pd.DataFrame) -> pd.DataFrame:
    """Return only unmitigated FVGs."""
    if fvg_df.empty:
        return fvg_df
    if "Mitigated" in fvg_df.columns:
        return fvg_df[~fvg_df["Mitigated"]].reset_index(drop=True)
    return fvg_df


# =========================================================
# VISUALISATION
# =========================================================

def plot_fvg(df: pd.DataFrame, fvg_df: pd.DataFrame,
             ticker: str = "", only_active: bool = False,
             max_fvgs: int = 50) -> None:
    """
    Plot a candlestick chart with matplotlib and overlay FVG zones
    as semi-transparent coloured rectangles.

    Parameters
    ----------
    df          : OHLC dataframe (DatetimeIndex).
    fvg_df      : Output of detect_fvg().
    ticker      : Label used in the chart title.
    only_active : If True, only unmitigated FVGs are drawn.
    max_fvgs    : Cap the number of boxes drawn (newest N kept).
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import Rectangle

    if fvg_df is None or fvg_df.empty:
        logging.warning("plot_fvg: no FVGs to plot.")
        return

    draw_df = active_fvg(fvg_df) if only_active else fvg_df.copy()
    if len(draw_df) > max_fvgs:
        draw_df = draw_df.tail(max_fvgs).reset_index(drop=True)

    # ── Use integer x-axis for reliable rectangle positioning ─────
    # Map timestamps → bar index so rectangles align with candles
    ts_to_idx = {ts: i for i, ts in enumerate(df.index)}
    x_vals    = np.arange(len(df))
    last_x    = len(df) - 1

    opens  = df["Open"].to_numpy()
    highs  = df["High"].to_numpy()
    lows   = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()

    # ── Figure setup ──────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(16, 7))
    fig.patch.set_facecolor("#0f0f0f")
    ax.set_facecolor("#141414")
    fig.suptitle(f"{ticker} — Fair Value Gaps", fontsize=13, color="#e0e0e0")

    # ── Candlestick drawing ───────────────────────────────────────
    BULL_C = "#26a69a"
    BEAR_C = "#ef5350"

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

    # ── FVG rectangles ────────────────────────────────────────────
    for _, row in draw_df.iterrows():
        is_bull     = row["Direction"] == "Bullish"
        face_color  = (0.149, 0.651, 0.604, 0.18) if is_bull else (0.937, 0.325, 0.314, 0.18)
        edge_color  = (0.149, 0.651, 0.604, 0.70) if is_bull else (0.937, 0.325, 0.314, 0.70)
        label_color = BULL_C if is_bull else BEAR_C

        x_start = ts_to_idx.get(row["Timestamp"], 0)

        # End at mitigation bar or extend to last candle
        mitigated = "Mitigated" in row and row["Mitigated"] and pd.notna(row.get("Mitigated_At"))
        if mitigated:
            x_end = ts_to_idx.get(row["Mitigated_At"], last_x)
        else:
            x_end = last_x

        width  = max(x_end - x_start, 1)          # at least 1 bar wide
        height = row["Top"] - row["Bottom"]

        ax.add_patch(Rectangle(
            (x_start, row["Bottom"]), width, height,
            facecolor=face_color, edgecolor=edge_color,
            linewidth=0.8, zorder=1
        ))

        # Label centred vertically at the left edge of the box
        ax.text(
            x_start + 0.3,
            row["Bottom"] + height / 2,
            "▲ FVG" if is_bull else "▼ FVG",
            color=label_color, fontsize=7,
            va="center", ha="left", zorder=4
        )

    # ── X-axis: show readable timestamps as tick labels ───────────
    n_ticks  = min(12, len(df))
    tick_pos = np.linspace(0, last_x, n_ticks, dtype=int)
    tick_lbl = [df.index[i].strftime("%d %b\n%H:%M") for i in tick_pos]
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_lbl, fontsize=7, color="#aaaaaa")
    ax.set_xlim(-1, last_x + 2)

    # ── Y-axis ───────────────────────────────────────────────────
    ax.tick_params(axis="y", colors="#aaaaaa", labelsize=8)
    ax.set_ylabel("Price", color="#aaaaaa", fontsize=9)

    # ── Grid & spines ─────────────────────────────────────────────
    ax.grid(True, alpha=0.12, color="#444444", linewidth=0.5)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333333")

    # ── Legend ────────────────────────────────────────────────────
    legend_handles = [
        mpatches.Patch(facecolor=BULL_C, alpha=0.5, label="Bullish FVG"),
        mpatches.Patch(facecolor=BEAR_C, alpha=0.5, label="Bearish FVG"),
    ]
    if "Mitigated" in fvg_df.columns:
        n_mit = fvg_df["Mitigated"].sum()
        n_act = (~fvg_df["Mitigated"]).sum()
        legend_handles += [
            mpatches.Patch(color="none", label=f"Active : {n_act}"),
            mpatches.Patch(color="none", label=f"Mitigated : {n_mit}"),
        ]
    ax.legend(
        handles=legend_handles, fontsize=8,
        facecolor="#1e1e1e", edgecolor="#444444", labelcolor="#e0e0e0",
        loc="upper left"
    )

    plt.tight_layout()
    plt.show()


# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    from Data_Manager import Download, download_daily_all

    tickers = ["BOMDYEING.NS"]
    Download(tickers)
    download_daily_all(tickers)

    for ticker in tickers:
        df = get_data(ticker, "15m")
        if df is None or df.empty:
            print(f"{ticker} — no data.")
            continue

        fvg_df = detect_fvg(df, mitigated=True)
        # print(f"\n{ticker} — {len(fvg_df)} FVGs detected")
        # print(fvg_df.to_string(index=False))

        active = active_fvg(fvg_df)
        print(f"\nActive (unmitigated): {len(active)}")

        plot_fvg(df, fvg_df, ticker=ticker, only_active=False)
