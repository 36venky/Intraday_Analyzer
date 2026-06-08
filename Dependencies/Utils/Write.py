from queue import Queue
from threading import Thread
import logging
import os

# =========================================================
# ASYNC FILE WRITER
# =========================================================

_write_queue = Queue()

# Project root: Dependencies/Utils/ -> Dependencies/ -> project root
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)
_SIGNALS_DIR = os.path.join(_PROJECT_ROOT, "Signals")


def _writer_worker():
    while True:
        try:
            filepath, text = _write_queue.get()
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            logging.error(f"Writer error: {e}")
        finally:
            _write_queue.task_done()


# Start writer thread once at import
Thread(target=_writer_worker, daemon=True, name="FileWriter").start()


def write(filename: str, text: str):
    """Async append text to a file inside the project's Signals/ folder."""
    os.makedirs(_SIGNALS_DIR, exist_ok=True)
    filepath = os.path.join(_SIGNALS_DIR, filename)
    _write_queue.put((filepath, text))


# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    write("test.txt", "Hello World !!\n")
    _write_queue.join()   # wait for write to complete before exit
    print("✅ Written to Signals/test.txt")
