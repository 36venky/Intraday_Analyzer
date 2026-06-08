# CustomLogger.py
import logging, os

# --- Custom log levels ---
BUY_LEVEL = 25
SELL_LEVEL = 26
THREAD_LEVEL = 27
CYCLE_LEVEL = 28
INVALID_LEVEL = 29
VALID_LEVEL = 30      # <-- NEW LEVEL

logging.addLevelName(BUY_LEVEL,    "BUY")
logging.addLevelName(SELL_LEVEL,   "SELL")
logging.addLevelName(THREAD_LEVEL, "THREAD")
logging.addLevelName(CYCLE_LEVEL,  "CYCLE")
logging.addLevelName(INVALID_LEVEL,"INVALID")
logging.addLevelName(VALID_LEVEL,  "VALID")   # <-- NEW LEVEL

def buy(self, msg, *args, **kwargs):
    self._log(BUY_LEVEL, f"🟢 {msg}", args, **kwargs)

def sell(self, msg, *args, **kwargs):
    self._log(SELL_LEVEL, f"🔴 {msg}", args, **kwargs)

def thread(self, msg, *args, **kwargs):
    self._log(THREAD_LEVEL, f"🚀 {msg}", args, **kwargs)

def cycle(self, msg, *args, **kwargs):
    self._log(CYCLE_LEVEL, f"🔄 {msg}", args, **kwargs)

def invalid(self, msg, *args, **kwargs):
    self._log(INVALID_LEVEL, f"❌ {msg}", args, **kwargs)

def isvalid(self, msg, *args, **kwargs):
    self._log(VALID_LEVEL, f"🤩 {msg}", args, **kwargs)   # <-- FIXED

logging.Logger.buy = buy
logging.Logger.sell = sell
logging.Logger.thread = thread
logging.Logger.cycle = cycle
logging.Logger.invalid = invalid
logging.Logger.isvalid = isvalid   # <-- ADDED


# --- Color formatter ---
class ColorFormatter(logging.Formatter):
    COLORS = {
        'INFO':     '\033[94m',
        'ERROR':    '\033[91m',
        'WARNING':  '\033[93m',
        'BUY':      '\033[92m',
        'SELL':     '\033[31m',
        'THREAD':   '\033[95m',
        'CYCLE':    '\033[96m',
        'INVALID':  '\033[90m',
        'VALID':    '\033[92m',    # <-- NEW COLOR
    }
    RESET = '\033[0m'

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        message = super().format(record)
        return f"{color}{message}{self.RESET}"


# --- Setup logger ---
#log_file = os.path.join(os.path.dirname(__file__), "Main.log")
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))  # project root
log_file = os.path.join(base_dir, "Logs", "Main.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)

logger = logging.getLogger("MainLogger")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))
logger.addHandler(file_handler)