"""
Helper script to build BlueBridge for the current platform using `flet build`.

Usage:
    python build.py                  # build for current platform
    python build.py windows          # Windows MSIX
    python build.py macos            # macOS app bundle
    python build.py linux            # Linux AppImage / deb
"""
from __future__ import annotations

import subprocess
import sys


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else _current_platform()
    _check_flutter()

    cmd = [
        sys.executable, "-m", "flet", "build", target,
        "--project", "BlueBridge",
        "--description", "Azure Navigator — navigate Azure faster than the portal",
        "--product", "BlueBridge",
        "--org", "com.bluebridge",
        "--build-version", "0.5.0",
        "--build-number", "5",
    ]

    # Include app icon if present
    import os
    if os.path.exists("assets/icons/icon.png"):
        cmd += ["--icon", "assets/icons/icon.png"]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


def _current_platform() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _check_flutter() -> None:
    result = subprocess.run(["flutter", "--version"], capture_output=True)
    if result.returncode != 0:
        print(
            "Flutter not found. `flet build` requires Flutter.\n"
            "Install: https://docs.flutter.dev/get-started/install"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
