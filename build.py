#!/usr/bin/env python3
"""Cross-platform PyInstaller build script for BlueBridge.

Usage:
    python build.py [windows|macos|linux]

Output:
    build/<platform>/BlueBridge/          (all platforms)
    build/macos/BlueBridge.app            (macOS .app bundle)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


def _version() -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', Path("pyproject.toml").read_text(), re.MULTILINE)
    if not m:
        raise RuntimeError("version not found in pyproject.toml")
    return m.group(1)


def _run(*args: str) -> None:
    print(f"  $ {' '.join(args)}")
    subprocess.run(list(args), check=True)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1].lower() not in ("windows", "macos", "linux"):
        print("Usage: python build.py [windows|macos|linux]")
        sys.exit(1)

    platform = sys.argv[1].lower()
    version = _version()
    print(f"BlueBridge {version} — building for {platform}")

    out_dir = Path("build") / platform
    out_dir.mkdir(parents=True, exist_ok=True)

    sep = os.pathsep  # ':' on Unix, ';' on Windows
    pyinstaller = [sys.executable, "-m", "PyInstaller"]

    cmd = [
        *pyinstaller,
        "launcher.py",
        "--name",
        "BlueBridge",
        "--onefile",
        "--collect-all",
        "streamlit",
        "--collect-all",
        "httpx",
        "--collect-all",
        "httpcore",
        "--add-data",
        f"app.py{sep}.",
        "--add-data",
        f"app{sep}app",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(out_dir),
    ]

    if platform == "macos":
        cmd += [
            "--windowed",
            "--osx-bundle-identifier",
            "com.bluebridge.app",
        ]
    elif platform == "windows":
        cmd += ["--windowed"]
        icon = Path("assets/icons/icon.ico")
        if icon.exists():
            cmd += ["--icon", str(icon)]
    # linux: no --windowed so the terminal stays visible

    _run(*cmd)

    if platform == "macos":
        bundle = out_dir / "BlueBridge.app"
        print(f"\n✓ macOS app bundle: {bundle}")
    else:
        exe_name = "BlueBridge.exe" if platform == "windows" else "BlueBridge"
        exe = out_dir / "BlueBridge" / exe_name
        print(f"\n✓ Executable: {exe}")


if __name__ == "__main__":
    main()
