import os
import logging
from datetime import datetime, time as dtime
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError

load_dotenv()

from Dependencies.Utils.Loggings import logger

# =========================================================
# CONNECTION
# =========================================================

_MONGO_URI = os.getenv("MONGO_URI")
_DB_NAME   = "Intraday_Analyzer"

if not _MONGO_URI:
    raise EnvironmentError("Missing MONGO_URI in .env")

_client = MongoClient(_MONGO_URI)
_db     = _client[_DB_NAME]

_MARKET_OPEN  = dtime(9, 15)
_MARKET_CLOSE = dtime(15, 15)


def _is_market_hours() -> bool:
    now = datetime.now()
    return (
        now.weekday() <= 4 and          # Mon–Fri
        _MARKET_OPEN <= now.time() <= _MARKET_CLOSE
    )


# =========================================================
# STORE SIGNAL
# =========================================================

def store_signal(strategy: str, ticker: str, signal: str, **kwargs):
    """
    Store a signal into a MongoDB collection named after the strategy.

    Args:
        strategy : collection name  e.g. "fluctuation", "smooth"
        ticker   : stock symbol     e.g. "IRCTC.NS"
        signal   : "BUY" or "SELL"
        **kwargs : any extra fields e.g. rsi=62.4, vwap=850.0

    Example:
        store_signal("fluctuation", "IRCTC.NS", "BUY", r2=0.91, price=845.5)
    """
    doc = {
        "ticker"    : ticker,
        "signal"    : signal,
        "timestamp" : datetime.now(),
        **kwargs
    }

    try:
        if not _is_market_hours():
            logger.debug(f"[{strategy}] Signal skipped — outside market hours.")
            return
        _db[strategy].insert_one(doc)
        logger.info(f"[{strategy}] ✅ {signal} stored for {ticker}.")
    except PyMongoError as e:
        logger.error(f"[{strategy}] ❌ DB insert failed for {ticker}: {e}")


# =========================================================
# FETCH SIGNALS
# =========================================================

def get_signals(strategy: str, ticker: str = None, limit: int = 50):
    """
    Fetch recent signals from a strategy collection.

    Args:
        strategy : collection name
        ticker   : filter by ticker (optional)
        limit    : max records to return (default 50)

    Returns:
        list of dicts
    """
    query = {"ticker": ticker} if ticker else {}

    try:
        cursor = (
            _db[strategy]
            .find(query, {"_id": 0})
            .sort("timestamp", ASCENDING)
            .limit(limit)
        )
        return list(cursor)
    except PyMongoError as e:
        logger.error(f"[{strategy}] ❌ DB fetch failed: {e}")
        return []


# =========================================================
# CLEAR COLLECTION  (use at EOD / reset)
# =========================================================

def clear_signals(strategy: str):
    """Delete all documents in a strategy collection."""
    try:
        result = _db[strategy].delete_many({})
        logger.info(f"[{strategy}] ✅ Cleared {result.deleted_count} signals.")
    except PyMongoError as e:
        logger.error(f"[{strategy}] ❌ DB clear failed: {e}")


# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    print("Storing test signals...")

    store_signal("fluctuation", "IRCTC.NS",  "BUY",  r2=0.91, price=845.5)
    store_signal("fluctuation", "CGPOWER.NS","SELL", r2=0.87, price=312.0)
    store_signal("smooth",      "IRCTC.NS",  "BUY",  distance=0.021)

    print("\nFetching fluctuation signals:")
    for s in get_signals("fluctuation"):
        print(s)

    print("\nFetching smooth signals for IRCTC.NS:")
    for s in get_signals("smooth", ticker="IRCTC.NS"):
        print(s)
    # clear_signals("fluctuation")
    # clear_signals("smooth")
