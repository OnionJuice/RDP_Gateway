#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="RDP Gateway"
APP_PATH="${ROOT_DIR}/dist/${APP_NAME}.app"
DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"

cd "${ROOT_DIR}"

echo "Syncing dependencies with uv..."
uv sync --default-index "${DEFAULT_INDEX}"

echo "Building macOS app with PyInstaller..."
uv run pyinstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "${APP_NAME}" \
  --osx-bundle-identifier "local.rdp-gateway" \
  scripts/macos_gui_entry.py

if command -v codesign >/dev/null 2>&1; then
  echo "Applying ad-hoc code signature..."
  codesign --force --deep --sign - "${APP_PATH}"
fi

if command -v xattr >/dev/null 2>&1; then
  echo "Removing quarantine attribute if present..."
  xattr -dr com.apple.quarantine "${APP_PATH}" 2>/dev/null || true
fi

echo "Built: ${APP_PATH}"
