#!/usr/bin/env bash
# Salin kode jarvis-tools dari laptop (WSL) ke server.
#  - Selalu menyalin ke ~/jarvis-tools-src di server (dipakai install.sh dan tes).
#  - Kalau sudah terpasang, kode di /opt/jarvis-tools ikut diperbarui tanpa sudo.
#    Perubahan systemd atau kunci SSH tetap perlu: sudo bash ~/jarvis-tools-src/install.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HOST="${HOST:-ai}"

rsync -a --delete --exclude '__pycache__' --exclude 'deploy.sh' "$HERE/" "$HOST:jarvis-tools-src/"
rsync -a "$HOME/.ssh/jarvis_tools.pub" "$HOST:jarvis-tools-src/jarvis_tools.pub"
echo "Kode tersalin ke $HOST:~/jarvis-tools-src"

if ssh "$HOST" 'test -w /opt/jarvis-tools/jarvis_tools'; then
    ssh "$HOST" 'install -m 644 ~/jarvis-tools-src/jarvis_tools/*.py /opt/jarvis-tools/jarvis_tools/ \
        && install -m 755 ~/jarvis-tools-src/bin/* /opt/jarvis-tools/bin/'
    echo "Kode di /opt/jarvis-tools sudah diperbarui."
else
    echo "Belum terpasang. Jalankan sekali di server: sudo bash ~/jarvis-tools-src/install.sh"
fi
