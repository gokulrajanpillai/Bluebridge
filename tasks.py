"""
Invoke task runner for BlueBridge.

Install:  pip install -e ".[dev]"
Usage:    invoke --list
          invoke run
          invoke build          # current platform
          invoke build --target windows
          invoke build --target macos
          invoke build --target linux
          invoke lint
          invoke clean
"""
from __future__ import annotations

import sys
from invoke import task


def _platform() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


@task
def run(c):
    """Start BlueBridge in desktop mode (requires a display)."""
    c.run("python main.py", pty=sys.platform != "win32")


@task
def web(c, port=8550):
    """Start BlueBridge in web mode — use this inside devcontainers or CI."""
    c.run(f"flet run main.py --web --port {port}", pty=sys.platform != "win32")


@task
def build(c, target=None):
    """Build a native executable. --target windows|macos|linux (default: current OS)."""
    t = target or _platform()
    valid = {"windows", "macos", "linux"}
    if t not in valid:
        print(f"Unknown target '{t}'. Choose from: {', '.join(sorted(valid))}")
        raise SystemExit(1)
    c.run(f"python build.py {t}")


@task
def build_all(c):
    """Build for all three platforms (requires each platform's toolchain)."""
    for t in ("windows", "macos", "linux"):
        print(f"\n{'─'*40}\nBuilding for {t}\n{'─'*40}")
        c.run(f"python build.py {t}")


@task
def lint(c):
    """Run ruff linter across the codebase."""
    c.run("ruff check .")


@task
def fmt(c):
    """Auto-format with ruff."""
    c.run("ruff format .")


@task
def clean(c):
    """Remove build artefacts and cache files."""
    patterns = ["build/", "dist/", "__pycache__", "*.pyc", "*.pyo", ".ruff_cache/"]
    if sys.platform == "win32":
        for p in patterns:
            c.run(f'if exist "{p}" rd /s /q "{p}" 2>nul || del /q "{p}" 2>nul', warn=True)
    else:
        c.run("rm -rf " + " ".join(patterns), warn=True)


@task
def install(c):
    """Install dependencies (including dev extras)."""
    c.run('pip install -e ".[dev]"')
