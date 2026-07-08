import pandas as pd
import os
import sys
from Data_Manager import get_data


def VWAP(ticker: str, interval: str = "15m") -> pd.Series:
    """
    Compute intraday VWAP, resetting at the start of each trading day.
    Returns a Series or empty Series on failure.
    """
    required = {"High", "Low", "Close", "Volume"}

    df = get_data(ticker, interval)

    if df is None or df.empty or not required.issubset(df.columns):
        return pd.Series(dtype=float)

    df = df.copy()

    tp = (df["High"] + df["Low"] + df["Close"]) / 3

    date_key        = df.index.normalize()
    tp_vol          = tp * df["Volume"]
    cumvol_by_day   = df.groupby(date_key)["Volume"].cumsum()
    cumtpvol_by_day = tp_vol.groupby(date_key).cumsum()

    return cumtpvol_by_day / cumvol_by_day
