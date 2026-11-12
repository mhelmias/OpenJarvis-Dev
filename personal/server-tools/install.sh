#!/usr/bin/env bash
# Pasang jarvis-tools di server. Jalankan dengan:
#   sudo bash ~/jarvis-tools-src/install.sh
# Aman dijalankan ulang untuk memperbarui kode, kunci SSH, dan systemd.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Jalankan dengan sudo: sudo bash $0" >&2
    exit 1
fi

SRC="$(cd "$(dirname "$0")" && pwd)"
OWNER="${SUDO_USER:-root}"
APP=/opt/jarvis-tools
DATA=/var/lib/jarvis-tools
CONF=/etc/jarvis-tools
PUBKEY="$SRC/jarvis_tools.pub"

say() { printf '\n== %s\n' "$*"; }

[ -s "$PUBKEY" ] || { echo "Kunci publik $PUBKEY tidak ditemukan. Jalankan deploy.sh dari laptop." >&2; exit 1; }
grep -q '^ssh-ed25519 ' "$PUBKEY" || { echo "Isi $PUBKEY bukan kunci ssh-ed25519." >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 tidak ditemukan." >&2; exit 1; }

say "Akun khusus jarvis (tanpa kata sandi, tanpa sudo)"
if ! id jarvis >/dev/null 2>&1; then
    useradd --system --home-dir "$DATA" --create-home --shell /bin/sh \
        --comment "OpenJarvis tools" jarvis
fi
usermod --password '*' jarvis
install -d -o jarvis -g jarvis -m 750 "$DATA"

say "Kode program di $APP (milik $OWNER, hanya bisa dibaca jarvis)"
install -d -o "$OWNER" -g "$OWNER" -m 755 "$APP" "$APP/bin" "$APP/jarvis_tools"
install -o "$OWNER" -g "$OWNER" -m 644 "$SRC"/jarvis_tools/*.py "$APP/jarvis_tools/"
install -o "$OWNER" -g "$OWNER" -m 755 "$SRC"/bin/* "$APP/bin/"
ln -sf "$APP/bin/jarvis-telegram-setup" /usr/local/sbin/jarvis-telegram-setup

say "Folder pengaturan $CONF"
install -d -o root -g jarvis -m 750 "$CONF"

say "Kunci SSH OpenJarvis (hanya boleh menjalankan program tool)"
install -d -o jarvis -g jarvis -m 700 "$DATA/.ssh"
printf 'restrict,command="%s/bin/jarvis-mcp" %s\n' "$APP" "$(tr -d '\r\n' < "$PUBKEY")" \
    > "$DATA/.ssh/authorized_keys"
chown jarvis:jarvis "$DATA/.ssh/authorized_keys"
chmod 600 "$DATA/.ssh/authorized_keys"

say "Pengirim pengingat (systemd, setiap menit)"
install -o root -g root -m 644 "$SRC"/systemd/jarvis-reminders.service \
    "$SRC"/systemd/jarvis-reminders.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now jarvis-reminders.timer
systemctl is-active jarvis-reminders.timer

if [ -t 0 ]; then
    say "Bot Telegram"
    if [ -s "$CONF/telegram.env" ]; then
        echo "Bot Telegram sudah diatur. Untuk mengganti: sudo jarvis-telegram-setup"
    else
        read -r -p "Sudah punya token dari @BotFather dan sudah menekan Start di bot itu? [y/N] " answer
        case "$answer" in
            [yY]*) /usr/local/sbin/jarvis-telegram-setup || echo "Bisa diulang nanti: sudo jarvis-telegram-setup" ;;
            *) echo "Nanti jalankan: sudo jarvis-telegram-setup" ;;
        esac
    fi
fi

say "Selesai"
