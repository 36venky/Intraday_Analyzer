import os
import glob

# Project root — two levels up from Dependencies/Features/
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__)))


def cleanup_folder(folder: str):
    """Delete all .txt, .log, .csv, .json files in the given folder.
    """
    path = os.path.join(_PROJECT_ROOT, folder)

    if not os.path.exists(path):
        print(f"⚠️  Folder not found: {path}")
        return

    for pattern in ("*.txt", "*.log", "*.csv", "*.json"):
        for file in glob.glob(os.path.join(path, pattern)):
            try:
                os.remove(file)
            except PermissionError:
                # File is locked (e.g. open in editor) — truncate instead
                try:
                    open(file, "w").close()
                except Exception:
                    pass
            except Exception as e:
                print(f"Failed to clear {file}: {e}")


def cleanup_project(tick=0):
    """
    Clean Signals and Logs folders at project root.
    No handler-closing needed — the RotatingFileHandler in Loggings.py
    uses delay=True so the file is not open until the first write.
    """
    if tick == 1:
        cleanup_folder("Signals")
        cleanup_folder("Logs")

# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    cleanup_project(1)
    print("✅ Cleanup complete.")
