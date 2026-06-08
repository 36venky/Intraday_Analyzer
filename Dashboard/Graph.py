import streamlit as st
from streamlit_autorefresh import st_autorefresh
import yfinance as yf
import pandas as pd
from datetime import datetime, time
import pytz

# -------------------------------
# CONFIG
# -------------------------------
st.set_page_config(layout="wide")
st.title("📈 Real-Time Candlestick Dashboard")

# -------------------------------
# MARKET CHECK
# -------------------------------
def is_market_open():
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    if now.weekday() >= 5:
        return False
    return time(9, 15) <= now.time() <= time(15, 30)

def adjust_interval(interval):
    if not is_market_open():
        st.caption("⚠️ Market closed → interval ≥5m")
        if interval in ["1m", "2m"]:
            return "5m"
    return interval

# -------------------------------
# VALID PERIODS
# -------------------------------
def get_valid_periods(interval):
    if interval == "1m":
        return ["1d", "5d"]
    elif interval in ["5m", "15m"]:
        return ["1d","2d", "5d","15d", "1mo"]
    return ["1d", "5d", "1mo", "3mo","6mo", "1y"]

from Features.UI import get_user_inputs,get_indicator_settings

inputs = get_user_inputs(get_valid_periods)
settings = get_indicator_settings()
tickers = inputs["tickers"]
interval = inputs["interval"]
period = inputs["period"]
refresh_rate = inputs["refresh_rate"]

from Features.render_dashboard import render_dashboard
render_dashboard(tickers, interval, period, settings)

# -------------------------------
# AUTO REFRESH
# -------------------------------
st.caption(f"Refreshing every {refresh_rate} sec")

st_autorefresh(
    interval=refresh_rate * 1000,
    key="dashboard_refresh"
)