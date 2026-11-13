#!/usr/bin/env bash
# Salin folder ini dari laptop (WSL) ke server, ke ~/jarvis-panel-src.
# Pemasangan pertama: sudo bash ~/jarvis-panel-src/install.sh (di server).
# Pembaruan kode: bash ~/jarvis-panel-src/build.sh lalu sudo systemctl restart jarvis-panel-web jarvis-panel-mcp
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HOST="${HOST:-ai}"

rsync -a --delete --exclude '__pycache__' --exclude 'deploy.sh' "$HERE/" "$HOST:jarvis-panel-src/"
echo "Tersalin ke $HOST:~/jarvis-panel-src"
