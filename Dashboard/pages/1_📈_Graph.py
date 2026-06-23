import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
from datetime import datetime, time
import pytz
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

st.title("📈 Real-Time Candlestick Dashboard")

# -------------------------------
# MARKET HOURS
# -------------------------------
IST = pytz.timezone("Asia/Kolkata")

def is_market_open():
    now = datetime.now(IST)
    if now.weekday() >= 5:          # Saturday / Sunday
        return False
    return time(9, 15) <= now.time() <= time(15, 15)

def adjust_interval(interval):
    if not is_market_open():
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
        return ["1d", "2d", "5d", "15d", "1mo"]
    return ["1d", "5d", "1mo", "3mo", "6mo", "1y"]

from Dashboard.Features.UI import get_user_inputs, get_indicator_settings
from Dashboard.Features.render_dashboard import render_dashboard

inputs   = get_user_inputs(get_valid_periods)
settings = get_indicator_settings()

tickers      = inputs["tickers"]
interval     = inputs["interval"]
period       = inputs["period"]
refresh_rate = inputs["refresh_rate"]

# -------------------------------
# MARKET STATUS + REFRESH BUTTON
# -------------------------------
market_open = is_market_open()
now_ist     = datetime.now(IST)

status_col, btn_col = st.columns([6, 1])

with status_col:
    if market_open:
        st.caption(
            f"🟢 Market open — auto-refreshing every **{refresh_rate}s**"
        )
    else:
        st.caption(
            f"🔴 Market closed ({now_ist.strftime('%H:%M IST')}) — "
            f"auto-refresh paused"
        )

with btn_col:
    if st.button("🔄 Refresh", use_container_width=False):
        st.cache_data.clear()
        st.rerun()

# -------------------------------
# CHARTS
# -------------------------------
render_dashboard(tickers, interval, period, settings)

# -------------------------------
# AUTO-REFRESH  (only during market hours)
# -------------------------------
if market_open:
    st_autorefresh(interval=refresh_rate * 1000, key="dashboard_refresh")
