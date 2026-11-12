#!/usr/bin/env bash
# Salin folder ini dari laptop (WSL) ke server, ke ~/openjarvis-src.
#  - Pemasangan pertama: sudo bash ~/openjarvis-src/install.sh (di server)
#  - jarvis-model yang terpasang ikut diperbarui hanya lewat install.sh (perlu sudo).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HOST="${HOST:-ai}"

rsync -a --delete --exclude 'deploy.sh' "$HERE/" "$HOST:openjarvis-src/"
echo "Tersalin ke $HOST:~/openjarvis-src"
