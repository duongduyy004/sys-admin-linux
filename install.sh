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
TARGET_DIR="/opt/sysadmin_gui"

sudo apt update
sudo apt install -y python3 python3-tk tree at tar zip unzip libnotify-bin policykit-1

sudo mkdir -p "$TARGET_DIR"
sudo cp -a "$SOURCE_DIR"/. "$TARGET_DIR"/
sudo chmod +x "$TARGET_DIR"/sh/*.sh
sudo chmod +x "$TARGET_DIR"/tests/*.sh
sudo chmod +x "$TARGET_DIR"/install.sh

sudo tee /usr/share/applications/sysadmin-gui.desktop >/dev/null <<'DESKTOP'
[Desktop Entry]
Name=SysAdmin GUI
Comment=Python GUI system administration tool
Exec=python3 /opt/sysadmin_gui/app.py
Icon=preferences-system
Terminal=false
Type=Application
Categories=System;Settings;
DESKTOP

bash "$TARGET_DIR/tests/self_test.sh"

echo "Installation complete. Launch SysAdmin GUI from the desktop menu."
