#!/usr/bin/env bash
#
# Kulma - install script
#
# Copies the scripts and systemd units into place. Does NOT enable the timers
# automatically, because config.json has to be edited first (photo folder,
# location) before anything is worth running.
#
set -euo pipefail

BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/kulma"
SYSTEMD_DIR="$HOME/.config/systemd/user"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Kulma - install"
echo "==============="

mkdir -p "$BIN_DIR" "$CONFIG_DIR" "$SYSTEMD_DIR"

cp "$SCRIPT_DIR/bin/kulma_index.py" "$BIN_DIR/"
cp "$SCRIPT_DIR/bin/kulma_wallpaper.py" "$BIN_DIR/"
cp "$SCRIPT_DIR/bin/kulma_i18n.py" "$BIN_DIR/"
chmod +x "$BIN_DIR/kulma_index.py" "$BIN_DIR/kulma_wallpaper.py"
echo "-> Scripts copied: $BIN_DIR"

cp "$SCRIPT_DIR/systemd/"*.service "$SCRIPT_DIR/systemd/"*.timer "$SYSTEMD_DIR/"
echo "-> Systemd units copied: $SYSTEMD_DIR"

if [ -f "$CONFIG_DIR/config.json" ]; then
    echo "-> config.json already exists, not overwriting ($CONFIG_DIR/config.json)"
else
    cp "$SCRIPT_DIR/config.example.json" "$CONFIG_DIR/config.json"
    echo "-> config.json created: $CONFIG_DIR/config.json"
fi

echo ""
echo "Next steps:"
echo "  1. Edit $CONFIG_DIR/config.json (photo folder, location, time zone)."
echo "     Do NOT use sudo to edit this file."
echo "  2. Run the first indexing:"
echo "       python3 $BIN_DIR/kulma_index.py"
echo "  3. Enable the timers:"
echo "       systemctl --user daemon-reload"
echo "       systemctl --user enable --now kulma.timer"
echo "       systemctl --user enable --now kulma-reindex.timer"
echo "  4. (Optional) to change the wallpaper also while logged out:"
echo "       loginctl enable-linger \$USER"
