'''
    Executions starts form here,
    This script will run all the analyzer scripts concurrently, allowing them to operate simultaneously without blocking each other.
'''

# Must be first — configures the root logger (file-only, no console output)
# before any other module can call logging.basicConfig or add a StreamHandler.
import Dependencies.Utils.Loggings  # noqa: F401

import subprocess
import glob
import os, time, sys

from Analyzer import *
from Data_Manager import *
from Dependencies.Utils import *
from Dependencies.Features import *

def run_all_analyzers():

    # ── One-time market open init (runs in master process only) ──
    reset_session()

    # Project root — one level up from this file
    project_root = os.path.dirname(os.path.abspath(__file__))

    # Modules now live inside Dependencies/
    mod_folder = os.path.join(project_root, "Dependencies", "Modules")

    # Find all scripts inside the mod folder that start with 'mod_'
    scripts = glob.glob(os.path.join(mod_folder, "mod_*.py"))

    if not scripts:
        print("⚠️ No mod_*.py files found inside 'Dependencies/Modules'!")
        return

    # Propagate PYTHONPATH so every subprocess can resolve project-root imports
    # when running WITHOUT `pip install -e .` (e.g. bare clone, CI without install step).
    # When the package IS installed this is a no-op — installed packages take precedence.
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        project_root + os.pathsep + existing_pp
        if existing_pp
        else project_root
    )

    processes = []
    for script in scripts:
        #print(f"🚀 Starting {os.path.basename(script)} ...")
        p = subprocess.Popen(
            [sys.executable, script],
            cwd=mod_folder,
            env=env,
        )
        processes.append(p)

    print("✅ All analyzer scripts are now running concurrently!\n")

    # Keep the master script alive until all analyzers finish
    for p in processes:
        p.wait()

if __name__ == "__main__":
    run_all_analyzers()