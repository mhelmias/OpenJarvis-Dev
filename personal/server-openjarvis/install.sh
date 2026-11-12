#!/usr/bin/env bash
# Pasang OpenJarvis di server ai. Jalankan dari akun admin:
#   sudo bash ~/openjarvis-src/install.sh
# Aman dijalankan ulang: konfigurasi, riwayat chat, dan kunci API yang sudah ada tidak ditimpa.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Jalankan dengan sudo: sudo bash $0" >&2
    exit 1
fi
ADMIN="${SUDO_USER:-}"
if [ -z "$ADMIN" ] || [ "$ADMIN" = "root" ]; then
    echo "Jalankan lewat sudo dari akun admin biasa, bukan langsung sebagai root." >&2
    exit 1
fi
SRC="$(cd "$(dirname "$0")" && pwd)"

if ! id jarvis >/dev/null 2>&1 || [ ! -x /opt/jarvis-tools/bin/jarvis-mcp ]; then
    echo "jarvis-tools belum terpasang. Pasang dulu: sudo bash ~/jarvis-tools-src/install.sh" >&2
    exit 1
fi
CHAT_ID="$(sed -n 's/^TELEGRAM_CHAT_ID=//p' /etc/jarvis-tools/telegram.env 2>/dev/null | head -n 1)"
if ! [[ "$CHAT_ID" =~ ^-?[0-9]+$ ]]; then
    echo "TELEGRAM_CHAT_ID belum ada. Atur dulu bot Telegram: sudo jarvis-telegram-setup" >&2
    exit 1
fi

echo "1/5 Membuat folder ..."
install -d -o "$ADMIN" -g "$ADMIN" -m 755 /opt/openjarvis
install -d -o jarvis -g jarvis -m 750 /var/lib/openjarvis
install -d -o root -g root -m 700 /etc/openjarvis
# Folder masuk untuk file dari Telegram, di dalam folder kerja yang dibuat install-excel.sh.
if getent group jarvis-files >/dev/null && [ -d /srv/jarvis-files ]; then
    install -d -o root -g jarvis-files -m 2770 /srv/jarvis-files/masuk
fi

CONFIG=/var/lib/openjarvis/config.toml
if [ ! -f "$CONFIG" ]; then
    sed "s/@CHAT_ID@/$CHAT_ID/" "$SRC/config.toml.template" > "$CONFIG"
    chown jarvis:jarvis "$CONFIG"
    chmod 640 "$CONFIG"
fi

echo "2/5 Memasang program jarvis-model dan layanan systemd ..."
install -o root -g root -m 755 "$SRC/bin/jarvis-model" /usr/local/sbin/jarvis-model
install -o root -g root -m 644 "$SRC/systemd/openjarvis.service" /etc/systemd/system/openjarvis.service
systemctl daemon-reload
systemctl enable openjarvis.service >/dev/null 2>&1

echo "3/5 Memasang alat build (compiler C, cmake) untuk modul Rust ..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || echo "Peringatan: apt-get update gagal, memakai daftar paket yang ada."
apt-get install -y -qq --no-install-recommends build-essential cmake pkg-config >/dev/null

echo "4/5 Membangun OpenJarvis sebagai $ADMIN (10-20 menit) ..."
sudo -u "$ADMIN" -H bash "$SRC/build.sh"

echo "5/5 Memilih model cloud ..."
if [ -f /etc/openjarvis/active.env ]; then
    echo "Model sudah pernah dipilih. Menjalankan ulang layanan ..."
    systemctl restart openjarvis.service
    /usr/local/sbin/jarvis-model status
elif [ -t 0 ]; then
    /usr/local/sbin/jarvis-model || echo "Model belum dipilih. Ulangi nanti dengan: sudo jarvis-model"
else
    echo "Pilih model nanti dengan: sudo jarvis-model"
fi
