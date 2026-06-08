import streamlit as st
# =====================================================
# USER INPUTS
# =====================================================
def get_user_inputs(get_valid_periods):

    col1, col2, col3, col4 = st.columns([2,1,1,1])

    with col1:
        ticker_input = st.text_input(
            "Tickers",
            "ETERNAL.NS"
        )

    with col2:
        interval = st.selectbox(
            "Interval",
            ["1m","5m","15m","1h","1d"]
        )

    with col3:
        period = st.selectbox(
            "Period",
            get_valid_periods(interval)
        )

    with col4:
        refresh_rate = st.number_input(
            "Refresh(s)",
            5,
            120,
            30
        )

    tickers = [
        t.strip().upper()
        for t in ticker_input.split(",")
        if t.strip()
    ]

    return {
        "tickers": tickers,
        "interval": interval,
        "period": period,
        "refresh_rate": refresh_rate
    }


# =====================================================
# SIDEBAR SETTINGS
# =====================================================
def get_indicator_settings():

    st.sidebar.title("Indicators")

    return {

        "show_ema":
            st.sidebar.checkbox(
                "EMA",
                value=False
            ),

        "show_swings":
            st.sidebar.checkbox(
                "Swing High/Low",
                value=False
            ),

        "show_supports":
            st.sidebar.checkbox(
                "Supports",
                value=False
            ),

        "show_resistance":
            st.sidebar.checkbox(
                "Resistance",
                value=False
            ),

        "show_trendlines":
            st.sidebar.checkbox(
                "Trendlines",
                value=False
            ),
        "show_line_chart":
            st.sidebar.checkbox(
                "Line Chart",
                value=False
            ),
    }