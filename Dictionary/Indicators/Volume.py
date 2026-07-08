import pandas as pd
import logging
import os
import sys
from Data_Manager import get_data


def Volume(ticker: str, length: int = 5, interval: str = "15m"):
    """
    Compare latest volume against its rolling VMA.

    Returns:
        (is_above_vma: bool, latest_volume: float, latest_vma: float)
        Returns (False, 0, 0) on invalid input.
    """
    df = get_data(ticker, interval)

    if df is None or df.empty or "Volume" not in df.columns:
        logging.warning(f"[{ticker}] Volume: no volume data available.")
        return False, 0, 0

    vol = df["Volume"].copy()
    vol = vol[~vol.index.duplicated(keep="last")]

    vma        = vol.rolling(window=length).mean()
    latest_vol = vol.iloc[-1]
    latest_vma = vma.iloc[-1]

    if hasattr(latest_vol, "item"): latest_vol = latest_vol.item()
    if hasattr(latest_vma, "item"): latest_vma = latest_vma.item()

    if pd.notnull(latest_vol) and pd.notnull(latest_vma):
        return latest_vol >= latest_vma, round(latest_vol, 2), round(latest_vma, 2)

    return False, 0, 0


def volume_ratio(ticker: str, interval: str = "15m", lookback_days: int = 5):
    """
    Computes intraday average volume ratio using stored MARKET_DATA.

        volume_ratio = today_avg_volume / past_avg_volume

    Where:
        - today_avg_volume = mean volume per candle today (so far)
        - past_avg_volume  = mean volume per candle over last N days,
                             time-aligned to same candle count as today

    Returns:
        (volume_ratio: float, today_avg: float, past_avg: float, rank3: np.ndarray)
        Returns None on insufficient data.
    """
    df = get_data(ticker, interval)

    if df is None or df.empty:
        logging.warning(f"[{ticker}] volume_ratio: no data available.")
        return None

    if "Volume" not in df.columns:
        logging.warning(f"[{ticker}] volume_ratio: Volume column missing.")
        return None

    # Add date column for grouping
    df = df.copy()
    df["date"] = df.index.normalize().date

    unique_days = sorted(df["date"].unique())

    if len(unique_days) < lookback_days + 1:
        logging.warning(
            f"[{ticker}] volume_ratio: need {lookback_days + 1} days, "
            f"got {len(unique_days)}."
        )
        return None

    today     = unique_days[-1]
    past_days = unique_days[-(lookback_days + 1):-1]

    # --- TODAY ---
    today_df     = df[df["date"] == today]
    candle_count = len(today_df)

    if candle_count == 0:
        logging.warning(f"[{ticker}] volume_ratio: no candles today.")
        return None

    today_avg = today_df["Volume"].mean()

    # --- PAST DAYS (time-aligned to today's candle count) ---
    past_avgs = []
    for day in past_days:
        day_df = df[df["date"] == day]
        if len(day_df) >= candle_count:
            past_avgs.append(day_df.iloc[:candle_count]["Volume"].mean())

    if not past_avgs:
        logging.warning(f"[{ticker}] volume_ratio: no valid past days.")
        return None

    past_avg = sum(past_avgs) / len(past_avgs)

    # --- LAST 3 CANDLE RANK ---
    vol3  = today_df["Volume"].tail(3).to_numpy()
    rank3 = pd.Series(vol3).rank().values

    ratio = today_avg / past_avg if past_avg > 0 else 0.0

    return round(ratio, 4), round(today_avg, 2), round(past_avg, 2), rank3


# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    from Data_Manager import Download

    tickers = ["SCI.NS", "IRCTC.NS", "CGPOWER.NS"]
    Download(tickers)

    for ticker in tickers:
        result = volume_ratio(ticker)
        if result:
            ratio, today_avg, past_avg, rank3 = result
            print(f"{ticker:<20} ratio={ratio:.2f}  today={today_avg:,.0f}  past={past_avg:,.0f}  rank3={rank3}")
        else:
            print(f"{ticker:<20} insufficient data")
