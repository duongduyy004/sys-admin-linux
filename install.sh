#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This installer is intended for Linux systems." >&2
  exit 1
fi

if [[ -f /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  case "${ID:-}" in
    ubuntu|debian|linuxmint) ;;
    *) echo "This installer is designed for Ubuntu-compatible systems." >&2; exit 1 ;;
  esac
fi

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="/opt/admindesk"
LEGACY_TARGET_DIR="/opt/sysadmin_gui"
LEGACY_DESKTOP_FILE="/usr/share/applications/sysadmin-gui.desktop"
APT_WARNING=0

sudo mkdir -p "$TARGET_DIR"
sudo cp -a "$SOURCE_DIR"/. "$TARGET_DIR"/
sudo chmod +x "$TARGET_DIR"/sh/*.sh
sudo chmod +x "$TARGET_DIR"/tests/*.sh
sudo chmod +x "$TARGET_DIR"/install.sh
sudo rm -rf "$LEGACY_TARGET_DIR"
sudo rm -f "$LEGACY_DESKTOP_FILE"

if ! sudo apt update; then
  APT_WARNING=1
  echo "Warning: 'apt update' failed. The project was still copied to $TARGET_DIR." >&2
  echo "Fix the Ubuntu package repository errors, then rerun the installer if you still need dependency installation." >&2
fi

if ! sudo apt install -y python3 python3-tk tree at tar zip unzip libnotify-bin policykit-1; then
  APT_WARNING=1
  echo "Warning: dependency installation did not complete. The project is present in $TARGET_DIR, but Ubuntu packages may still be missing." >&2
fi

sudo tee /usr/share/applications/admindesk.desktop >/dev/null <<'DESKTOP'
[Desktop Entry]
Name=AdminDesk
Comment=Python GUI system administration tool
Exec=/usr/bin/python3 /opt/admindesk/app.py
TryExec=/usr/bin/python3
Icon=preferences-system
Terminal=false
Type=Application
Categories=System;Settings;
DESKTOP

bash "$TARGET_DIR/tests/self_test.sh"

if [[ "$APT_WARNING" -eq 1 ]]; then
  echo "Installation finished with package warnings. Launch AdminDesk from the desktop menu after fixing the apt repository issues."
else
  echo "Installation complete. Launch AdminDesk from the desktop menu."
fi
