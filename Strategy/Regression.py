import os
from datetime import datetime

from Dictionary.Indicators import *
from Data_Manager import *
from Dependencies.Features import *
from Dependencies.Utils import is_fluctuation, write, smooth, add_value
from Dimension.confluence import validate_signal
from Dimension.snapshot   import capture as snap

_STRATEGY = "regression"

# =========================================================
# REGRESSION STRATEGY
# =========================================================

def Regression(ticker: str):
    """
    Computes R², volume ratio and DTW smooth score for a ticker.
    Writes signal to the appropriate file based on thresholds.
    Skips if the same signal already fired this session.
    """
    r2 = is_fluctuation(ticker)
    if not r2 or r2 == 1 or r2 == 0:
        return

    vol   = volume_ratio(ticker)
    ratio = vol[0] if vol is not None else 0

    sm = smooth(ticker) or 0

    ts = datetime.now().strftime("%H:%M:%S")

    # ── Rolling R² momentum tracking ──────────────────────
    signal_hit, near, mean_diff, latest, history = add_value(ticker, r2)

    if signal_hit:
        hist_signal = "RHIST"
        if not state.has_fired(_STRATEGY, ticker, hist_signal):
            state.record(_STRATEGY, ticker, hist_signal)
            write(
                "RegHistory.txt",
                f"{ts},{ticker},r2={latest:.2f},mean_diff={mean_diff:.2f},"
                f"near={near},history={history[-3:]}\n"
            )
    else:
        write(
            "Invalid_RegHistory.txt",
            f"{ts},{ticker},r2={latest:.2f},mean_diff={mean_diff:.2f},"
            f"near={near},history={history[-3:]}\n")
    # ──────────────────────────────────────────────────────

    if r2 >= 0.93 and ratio >= 1.7:
        signal = "REG"
        if not state.has_fired(_STRATEGY, ticker, signal):

            # ── HTF confluence check ──────────────────────
            price  = get_data(ticker, "1m")
            price  = float(price["Close"].iloc[-1]) if price is not None and not price.empty else 0.0
            cf     = validate_signal(ticker, "BUY", price)
            final  = cf["final_signal"]    # BUY or SELL after HTF filter
            cf_tag = f"{cf['action']}:{cf['timeframe'] or 'raw'}"
            # ─────────────────────────────────────────────

            state.record(_STRATEGY, ticker, signal)
            write("Reg.txt", f"{ts},{ticker},{r2:.2f},{sm:.4f},{ratio:.2f},{final},{cf_tag}\n")
            store_signal(_STRATEGY, ticker, signal, r2=r2, sm=sm, ratio=ratio,
                         cf_signal=final, cf_reason=cf["reason"])
            snap(ticker, strategy=_STRATEGY, signal=final, price=price)

    elif r2 >= 0.85 and sm <= 0.03 and ratio > 1.5:
        signal = "VOL"
        if not state.has_fired(_STRATEGY, ticker, signal):

            # ── HTF confluence check ──────────────────────
            price  = get_data(ticker, "1m")
            price  = float(price["Close"].iloc[-1]) if price is not None and not price.empty else 0.0
            cf     = validate_signal(ticker, "BUY", price)
            final  = cf["final_signal"]
            cf_tag = f"{cf['action']}:{cf['timeframe'] or 'raw'}"
            # ─────────────────────────────────────────────

            state.record(_STRATEGY, ticker, signal)
            write("Vol.txt", f"{ts},{ticker},{r2:.2f},{sm:.4f},{ratio:.2f},{final},{cf_tag}\n")
            store_signal(_STRATEGY, ticker, signal, r2=r2, sm=sm, ratio=ratio,
                         cf_signal=final, cf_reason=cf["reason"])
            snap(ticker, strategy="vol", signal=final, price=price)
    else:
        write("Invalid_Reg.txt", f"{ts},{ticker},{r2:.2f},{sm:.4f},{ratio:.2f}\n")


# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    from Data_Manager import Download, get_ticker

    tickers = ["MASPTOP50.NS"]
    print(f"Downloading 1m data for {len(tickers)} tickers...")
    Download(tickers)

    for ticker in tickers:
        Regression(ticker)

    print("✅ Done. Check Signals/")
