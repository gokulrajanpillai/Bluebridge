#!/usr/bin/env bash
# Build a Mac Intel (x86_64) DMG for BlueBridge.
# Requirements: macOS, Python 3.11+, pip, hdiutil (built-in on macOS).
# Usage: ./build_dmg.sh

set -euo pipefail

APP="BlueBridge"
DIST="dist"
STAGING="$DIST/dmg_staging"

# ── Version from pyproject.toml ───────────────────────────────────────────────
VERSION=$(python3 -c "
import tomllib, pathlib
d = tomllib.loads(pathlib.Path('pyproject.toml').read_text())
print(d['project']['version'])
")
echo "→ Building $APP $VERSION (mac-intel)"

# ── Dependencies ──────────────────────────────────────────────────────────────
pip install --quiet pyinstaller streamlit httpx

# ── PyInstaller bundle ────────────────────────────────────────────────────────
# Collect all Streamlit static assets automatically via --collect-all.
# app.py and the app/ package are added as data so the bundled app can find them.
pyinstaller launcher.py \
  --name "$APP" \
  --windowed \
  --onedir \
  --target-arch x86_64 \
  --collect-all streamlit \
  --add-data "app.py:." \
  --add-data "app:app" \
  --noconfirm \
  --clean

APP_BUNDLE="$DIST/$APP.app"
if [ ! -d "$APP_BUNDLE" ]; then
  echo "✗ PyInstaller did not produce $APP_BUNDLE" >&2
  exit 1
fi

# ── Stage DMG contents ────────────────────────────────────────────────────────
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp -r "$APP_BUNDLE" "$STAGING/"
ln -sf /Applications "$STAGING/Applications"

# ── Create DMG ────────────────────────────────────────────────────────────────
DMG="$DIST/${APP}-${VERSION}-mac-intel.dmg"
hdiutil create \
  -volname "$APP $VERSION" \
  -srcfolder "$STAGING" \
  -ov \
  -format UDZO \
  "$DMG"

rm -rf "$STAGING"

echo "✓ $DMG"
echo ""
echo "To install: open $DMG, drag $APP to Applications."
