import streamlit as st
import os
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

st_autorefresh(interval=3000, key="refresh")

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))        # Dashboard/Utils/
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))  # project root
LOG_DIR      = os.path.join(PROJECT_ROOT, "Signals")

st.set_page_config(page_title="Stock Dashboard", layout="wide")

st.title("📊 Stock Signals Dashboard")

# 🔍 Filters
col1, col2, col3, col4 = st.columns(4)

with col1:
    search = st.text_input("Search")

with col2:
    signal_filter = st.selectbox("Signal", ["", "BUY", "SELL"])

with col3:
    files = [f for f in os.listdir(LOG_DIR) if f.endswith(".txt")]
    file_filter = st.selectbox("File", [""] + files)

with col4:
    limit = st.number_input("Rows per file", value=200)

# 📊 Load Data
data = []   # ✅ initialize ONCE

def parse_line(file, parts):
    
    if "Buy" in file or "Sell" in file:
        if len(parts) != 8:
            return None
        
        keys = ["Ticker","Price","DateTime","Time","Score","Metric1","Array","FinalScore"]

    elif "Invalid" in file:
        if len(parts) != 5:
            return None
        
        keys = ["Time","Ticker","Value1","Value2","Array"]

    elif "Smooth" in file:
        if len(parts) != 5:
            return None
        
        keys = ["Time","Ticker","Value","Score","SignalType"]
    
    elif "Reg" in file:
        if len(parts) > 9:
            return None
        
        keys = ["Time","Ticker","Value","Score","SignalType","Metric1","Metric2","Metric3","Array"]
    
    elif "Valid" in file:
        if len(parts) > 9:
            return None
        
        keys = ["Time","Ticker","Value","Score","SignalType","Metric1","Metric2","Metric3","Array"]
    
    elif "Count" in file:
        if len(parts) > 9:
            return None
        
        keys = ["Time","Ticker","Value","Score","SignalType","Metric1","Metric2","Metric3","Array"]

    else:
        return None

    return dict(zip(keys, parts))


for file in os.listdir(LOG_DIR):
    if not file.endswith(".txt"):
        continue

    if file_filter and file != file_filter:
        continue

    path = os.path.join(LOG_DIR, file)

    try:
        with open(path, "r") as f:
            lines = f.readlines()[-limit:]

        for line in reversed(lines):
            parts = line.strip().split(",")

            parsed = parse_line(file, parts)

            if not parsed:
                continue

            # 🔍 GLOBAL SEARCH (works across all files now)
            if search and search.lower() not in line.lower():
                continue

            # 🔎 Signal filter
            if signal_filter:
                if parsed.get("SignalType") != signal_filter and parsed.get("Score") != signal_filter:
                    continue

            parsed["Source"] = file
            data.append(parsed)

    except Exception as e:
        st.error(f"Error reading {file}: {e}")

# 🔽 Sort latest first
data = sorted(data, key=lambda x: x["Time"], reverse=True)

# 📋 Display
st.dataframe(data, width="stretch")