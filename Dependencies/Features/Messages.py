import threading
import time
import os
from queue import Queue
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

# =========================================================
# LOGGER
# =========================================================
from Dependencies.Utils.Loggings import logger

# =========================================================
# TWILIO CONFIG
# =========================================================

SID         = os.getenv("SID")
TOKEN       = os.getenv("TOKEN")
FROM_NUMBER = 'whatsapp:+14155238886'
TO_NUMBER   = os.getenv("TO_NUMBER")

if not all([SID, TOKEN, TO_NUMBER]):
    raise EnvironmentError(
        "Missing Twilio credentials. Check SID, TOKEN, TO_NUMBER in .env"
    )

# =========================================================
# WORKER
# =========================================================

message_queue  = Queue()
_worker_thread = None


def _whatsapp_worker():
    logger.info("✅ WhatsApp worker started.")
    client = Client(SID, TOKEN)

    while True:
        msg = message_queue.get()

        if msg is None:
            message_queue.task_done()
            break

        try:
            client.messages.create(
                from_=FROM_NUMBER,
                to=TO_NUMBER,
                body=msg
            )
            logger.info(f"📤 WhatsApp sent: {msg}")
        except Exception as e:
            logger.error(f"❌ WhatsApp send error: {e}")
        finally:
            message_queue.task_done()

        time.sleep(1)

    logger.info("🛑 WhatsApp worker stopped.")


def start_whatsapp_worker():
    """Start background worker once only."""
    global _worker_thread

    if _worker_thread and _worker_thread.is_alive():
        logger.debug("WhatsApp worker already running — skipped.")
        return

    _worker_thread = threading.Thread(
        target=_whatsapp_worker,
        daemon=True,
        name="WhatsAppWorker"
    )
    _worker_thread.start()


def stop_whatsapp_worker():
    """Gracefully stop the worker."""
    message_queue.put(None)


def send(message: str):
    """Queue a WhatsApp message. Auto-starts worker if needed."""
    start_whatsapp_worker()
    message_queue.put(message)


# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    print(f"SID      : {SID[:6]}..." if SID else "SID      : ❌ NOT SET")
    print(f"TOKEN    : {TOKEN[:6]}..." if TOKEN else "TOKEN    : ❌ NOT SET")
    print(f"TO_NUMBER: {TO_NUMBER}" if TO_NUMBER else "TO_NUMBER: ❌ NOT SET")
    print(f"FROM     : {FROM_NUMBER}")

    send("🚀 Test message from Intraday Analyzer")

    message_queue.join()
    print("✅ Done.")
