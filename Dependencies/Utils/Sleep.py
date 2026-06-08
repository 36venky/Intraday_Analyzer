import time
import logging
from datetime import datetime, timedelta


def wait_until_next_candle(interval: str = "15m"):
    """
    Sleep until the next candle open for the given interval.

    Supported intervals: 1m, 3m, 5m, 15m, 30m, 1h, 1d
    """
    interval_minutes = {
        "1m" : 1,
        "3m" : 3,
        "5m" : 5,
        "15m": 15,
        "30m": 30,
        "1h" : 60,
        "1d" : 1440,
    }

    minutes = interval_minutes.get(interval)

    if minutes is None:
        raise ValueError(
            f"Unsupported interval '{interval}'. "
            f"Choose from: {list(interval_minutes.keys())}"
        )

    now       = datetime.now()
    next_time = (now + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
    next_time -= timedelta(minutes=next_time.minute % minutes)

    wait_seconds = max(0, (next_time - now).total_seconds())

    logging.info(
        f"[{interval}] Waiting {int(wait_seconds)}s "
        f"until next candle at {next_time.strftime('%H:%M:%S')}"
    )

    time.sleep(wait_seconds)
