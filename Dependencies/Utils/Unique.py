import os
import sys
import logging
from datetime import datetime, time as dtime
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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