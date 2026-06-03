"""
launch.py — Wisuno Studio launcher
Runs uvicorn IN-PROCESS (not as a subprocess) for maximum stability.
"""
import os
import sys
import threading
import time
import webbrowser
import subprocess
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
THIS_FILE   = Path(__file__).resolve()
STUDIO_DIR  = THIS_FILE.parent
PROJECT_DIR = STUDIO_DIR.parent
BACKEND_DIR = STUDIO_DIR / "backend"
PYTHON      = Path(sys.executable)
REQS        = BACKEND_DIR / "requirements_studio.txt"

URL = "http://localhost:8000"

def install_deps():
    print("  [1/2] Checking studio dependencies...")
    result = subprocess.run(
        [str(PYTHON), "-m", "pip", "install", "-q", "-r", str(REQS)],
        cwd=str(PROJECT_DIR),
    )
    if result.returncode != 0:
        print("\n  [ERROR] Failed to install dependencies.")
        input("  Press Enter to exit...")
        sys.exit(1)
    print("         OK.\n")

def open_browser_when_ready():
    """Poll /health then open the browser."""
    import urllib.request
    for _ in range(20):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"{URL}/health", timeout=2)
            webbrowser.open(URL)
            print(f"\n  ✓ Browser opened at {URL}")
            print("  Keep this window open. Close it to stop the server.\n")
            return
        except Exception:
            pass
    print("\n  [WARNING] Could not confirm server is ready. Try opening manually:")
    print(f"  {URL}\n")

def main():
    print()
    print("  =========================================")
    print("   WISUNO STUDIO — Starting up...")
    print("  =========================================")
    print(f"  Project : {PROJECT_DIR}")
    print(f"  Python  : {PYTHON}")
    print()

    # Make sure project root is importable
    if str(PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR))
    backend_dir = str(BACKEND_DIR)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    # Set encoding
    os.environ["PYTHONUTF8"] = "1"

    install_deps()

    # Open browser in background thread (non-blocking)
    threading.Thread(target=open_browser_when_ready, daemon=True).start()

    # Run uvicorn IN-PROCESS — this is the most stable approach
    print("  [2/2] Starting server at http://localhost:8000 ...")
    print("  =========================================")
    print("   Open:  http://localhost:8000")
    print("   Stop:  Ctrl+C or close this window")
    print("  =========================================\n")

    try:
        import uvicorn
        uvicorn.run(
            "studio.backend.app:app",
            host="127.0.0.1",
            port=8000,
            log_level="info",
        )
    except ImportError:
        print("\n  [ERROR] uvicorn not found. Installing now...")
        subprocess.run([str(PYTHON), "-m", "pip", "install", "uvicorn[standard]"])
        import uvicorn
        uvicorn.run(
            "studio.backend.app:app",
            host="127.0.0.1",
            port=8000,
            log_level="info",
        )
    except KeyboardInterrupt:
        print("\n  Server stopped.")

if __name__ == "__main__":
    main()
