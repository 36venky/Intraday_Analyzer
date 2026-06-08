import pandas as pd
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Data_Manager import get_data


def EMA(ticker: str, length: int, interval: str = "15m") -> pd.Series:
    """
    Compute Exponential Moving Average on the Close column.
    Returns a Series or empty Series on failure.
    """
    df = get_data(ticker, interval)

    if df is None or df.empty or "Close" not in df.columns:
        return pd.Series(dtype=float)

    return df["Close"].ewm(span=length, adjust=False).mean()
