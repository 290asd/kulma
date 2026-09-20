#!/usr/bin/env bash
#
# Kulma - asennusskripti
#
# Kopioi skriptit ja systemd-yksiköt paikoilleen. EI ota timereitä käyttöön
# automaattisesti, koska config.json pitää muokata ensin (kuvakansio,
# sijainti) ennen kuin mitään kannattaa ajaa.
#
set -euo pipefail

BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/kulma"
SYSTEMD_DIR="$HOME/.config/systemd/user"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Kulma - asennus"
echo "==============="

mkdir -p "$BIN_DIR" "$CONFIG_DIR" "$SYSTEMD_DIR"

cp "$SCRIPT_DIR/bin/kulma_index.py" "$BIN_DIR/"
cp "$SCRIPT_DIR/bin/kulma_wallpaper.py" "$BIN_DIR/"
chmod +x "$BIN_DIR/kulma_index.py" "$BIN_DIR/kulma_wallpaper.py"
echo "-> Skriptit kopioitu: $BIN_DIR"

cp "$SCRIPT_DIR/systemd/"*.service "$SCRIPT_DIR/systemd/"*.timer "$SYSTEMD_DIR/"
echo "-> Systemd-yksiköt kopioitu: $SYSTEMD_DIR"

if [ -f "$CONFIG_DIR/config.json" ]; then
    echo "-> config.json on jo olemassa, ei ylikirjoiteta ($CONFIG_DIR/config.json)"
else
    cp "$SCRIPT_DIR/config.example.json" "$CONFIG_DIR/config.json"
    echo "-> config.json luotu: $CONFIG_DIR/config.json"
fi

echo ""
echo "Seuraavaksi:"
echo "  1. Muokkaa $CONFIG_DIR/config.json (kuvakansio, sijainti, aikavyöhyke)."
echo "     ÄLÄ käytä sudoa tämän tiedoston muokkaamiseen."
echo "  2. Aja ensimmäinen indeksointi:"
echo "       python3 $BIN_DIR/kulma_index.py"
echo "  3. Ota timerit käyttöön:"
echo "       systemctl --user daemon-reload"
echo "       systemctl --user enable --now kulma.timer"
echo "       systemctl --user enable --now kulma-reindex.timer"
echo "  4. (Valinnainen) jos haluat taustakuvan vaihtuvan myös uloskirjautuneena:"
echo "       loginctl enable-linger \$USER"
