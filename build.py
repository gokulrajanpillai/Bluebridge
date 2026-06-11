"""
Helper script to build BlueBridge for the current platform using `flet build`.

Cross-compilation is NOT supported by flet/Flutter — each target must be built
on its native OS (Windows → MSIX, macOS → .app, Linux → AppImage/deb).
The GitHub Actions release workflow handles all three in parallel.

Usage:
    python build.py                  # build for current platform
    python build.py linux            # Linux AppImage / deb
    python build.py windows          # must run on Windows
    python build.py macos            # must run on macOS
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def _flet_cmd() -> list[str]:
    """Return the command list to invoke the flet CLI.

    Prefer the standalone `flet` executable on PATH (installed by pip).
    Fall back to `python -m flet` so it works even when the Scripts/bin
    directory is not on PATH (common on fresh CI runners on Windows).
    """
    if shutil.which("flet"):
        return ["flet"]
    return [sys.executable, "-m", "flet"]


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else _current_platform()
    _check_cross_compile(target)
    _check_deps()

    cmd = _flet_cmd() + [
        "build",
        target,
        "--verbose",
        "--project",
        "BlueBridge",
        "--description",
        "Azure Navigator — navigate Azure faster than the portal",
        "--product",
        "BlueBridge",
        "--org",
        "com.bluebridge",
        "--build-version",
        "0.5.0",
        "--build-number",
        "5",
    ]

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


def _check_cross_compile(target: str) -> None:
    host = _current_platform()
    if target == host:
        return
    print(
        f"Cannot build '{target}' on '{host}': flet/Flutter does not support cross-compilation.\n"
        "\n"
        "  • Build linux   → run inside the devcontainer (Linux)\n"
        "  • Build windows → run on Windows  (or push a tag to trigger GitHub Actions)\n"
        "  • Build macos   → run on macOS    (or push a tag to trigger GitHub Actions)\n"
        "\n"
        "Push a version tag (e.g. git tag v1.0.0 && git push --tags) to build all\n"
        "three platforms in parallel via GitHub Actions."
    )
    sys.exit(1)


def _check_deps() -> None:
    # Verify flet is importable (covers both `flet` on PATH and python -m flet).
    try:
        subprocess.run(
            [sys.executable, "-c", "import flet"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        print("flet is not installed. Run: pip install -e '.[dev]'")
        sys.exit(1)

    # Verify flutter is on PATH — required by flet build.
    if not shutil.which("flutter"):
        print(
            "flutter not found on PATH.\n"
            "Inside the devcontainer: rebuild the container (Dockerfile now installs Flutter).\n"
            "Outside: https://docs.flutter.dev/get-started/install"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
