import streamlit as st
import yfinance as yf
import pandas as pd


@st.cache_data(ttl=5)
def fetch_clean_data(ticker, interval, period):
    try:
        df = yf.download(
            ticker,
            interval=interval,
            period=period,
            progress=False,
            auto_adjust=True
        )
    except:
        return None

    if df.empty:
        return None

    # Flatten columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[['Open','High','Low','Close']].copy()

    # Timezone fix
    try:
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")

        df.index = df.index.tz_convert("Asia/Kolkata")
    except:
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Kolkata')

    # Market hours filter
    df = df.between_time("09:15", "15:30")

    df = df.apply(pd.to_numeric, errors='coerce').dropna()

    return df if not df.empty else None