import numpy as np
import yfinance as yf
import pandas as pd
import math
import logging
from sklearn.linear_model import LinearRegression
from datetime import datetime


def is_fluctuation(ticker):
    data = get_data(ticker, '1m')
    
    if data is None:
        return False, 0

    df = data
    end_index = len(df)
    #start = max(0,end_index-60)
    df_slice = df.iloc[0:end_index]

    # --- Volatility Calculation ---
    returns = df_slice['Close'].pct_change().dropna()
    volatility = returns.std()

    # --- Linear regression ---
    y = df_slice['Close'].values.reshape(-1, 1)
    z = len(y)
    x = np.arange(z).reshape(-1, 1)
    model = LinearRegression().fit(x, y)

    r2 = model.score(x, y)
    r2 = round(r2,2)
    slope = model.coef_[0][0]

    # Convert slope to angle
    angle = math.degrees(math.atan(slope))

    # --- Sideways detection ---
    price_range = df_slice['High'].max() - df_slice['Low'].min()
    avg_price = df_slice['Close'].mean()
    range_percent = (price_range / avg_price) * 100

    # --- Time based volatility threshold ---
    now = datetime.now().strftime("%H:%M")

    if now < "10:00":
        vol_threshold = 0.006
    else:
        vol_threshold = 0.004

    # --- Final logic ---
    if (volatility < vol_threshold and r2 >= 0.80 ) :#or (r2 >= 0.92):
        line = (f"{datetime.now().strftime('%H:%M:%S')},{ticker},{volatility:.4f},{angle:.2f},{range_percent:.2f},[{z}],{r2:.2f}")
        return True , r2

    else:
        line = (f"{datetime.now().strftime('%H:%M:%S')},{ticker},{volatility:.4f},{angle:.2f},{range_percent:.2f},[{z}],{r2:.2f}")
        return False , r2

# =========================================================
# TRAIL RUN
# =========================================================

def main():
    import sys
    import os
    import time
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from Data_Manager import Download, get_data

    tickers = ['CGPOWER', 'IRCTC', 'DABUR', 'DLF', 'MARICO', 'SUNTV', 'UPL', 'TATACHEM', 'TATATECH', 'TANLA']
    tickers = [t + '.NS' for t in tickers]

    print(f"Downloading 1m data for {len(tickers)} tickers...")
    Download(tickers)

    print("\n{:<20} {:<10} {:<8}".format("Ticker", "Fluct?", "R²"))
    print("-" * 40)

    for ticker in tickers:
        result, r2 = is_fluctuation(ticker)
        status = "✅ YES" if result else "❌ NO"
        print("{:<20} {:<10} {:.2f}".format(ticker, status, r2))


if __name__ == "__main__":
    main()
