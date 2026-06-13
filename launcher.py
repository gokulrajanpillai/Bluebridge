"""PyInstaller entry point — starts Streamlit and opens the system browser."""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

_PORT = 8501


def _open_browser() -> None:
    # Give Streamlit a few seconds to bind the port before opening the browser.
    time.sleep(3.0)
    webbrowser.open(f"http://localhost:{_PORT}")


def main() -> None:
    # Resolve app.py: when frozen it lives in sys._MEIPASS, else beside this file.
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    app_py = os.path.join(base, "app.py")

    # Open the browser in a background thread so we don't block stcli.main().
    threading.Thread(target=_open_browser, daemon=True).start()

    from streamlit.web import cli as stcli  # noqa: PLC0415

    sys.argv = [
        "streamlit",
        "run",
        app_py,
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        f"--server.port={_PORT}",
        "--browser.serverAddress=localhost",
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
