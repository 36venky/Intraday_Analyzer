import os
import sys
import logging

from Data_Manager import *

# =========================================================
# SIGNAL STATE
# =========================================================

class SignalState:
    """
    Tracks last-fired signal per ticker per strategy.
    Prevents duplicate signals from firing on consecutive candles.
    """

    def __init__(self):
        # { strategy_name: { ticker: last_signal } }
        self._state = {}

    def has_fired(self, strategy: str, ticker: str, signal: str) -> bool:
        """Returns True if this exact signal already fired for this ticker."""
        return self._state.get(strategy, {}).get(ticker) == signal

    def record(self, strategy: str, ticker: str, signal: str):
        """Record that a signal fired."""
        if strategy not in self._state:
            self._state[strategy] = {}
        self._state[strategy][ticker] = signal

    def reset(self, strategy: str, ticker: str):
        """Clear signal state for a ticker (e.g. on new candle or exit)."""
        if strategy in self._state:
            self._state[strategy].pop(ticker, None)

    def reset_all(self):
        """Clear everything — called at market open."""
        self._state.clear()
        logging.info("SignalState reset.")


# Single global instance shared across all strategies
state = SignalState()

# =========================================================
# MARKET OPEN INITIALIZER
# =========================================================

_initialized = False   # ensures it runs only once per session

def Daily_Data(tickers):
    """
    Runs once when execution starts between 9:30 and 9:45.
    Downloads 1d data for all tickers.
    Call reset_session() before this to wipe previous state.
    """
    global _initialized

    if _initialized:
        logging.info("Daily_Data already ran. Skipping.")
        return

    logging.info("🔄 Daily_Data running...")

    download_daily_all(tickers)

    _initialized = True
    logging.info("✅ Daily_Data complete.")


def reset_session():
    """
    Wipes signal state and re-arms Daily_Data for the next run.
    Call this at startup or EOD.
    """
    global _initialized
    _initialized = False
    state.reset_all()
    logging.info("Session reset. Ready for next market open.")
