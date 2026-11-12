#!/usr/bin/env bash
# Pasang tool Excel untuk OpenJarvis di server. Jalankan dari akun admin:
#   sudo bash ~/jarvis-tools-src/install-excel.sh
# Membuat folder kerja /srv/jarvis-files, layanan jarvis-excel, lalu menyambungkannya ke OpenJarvis.
# Aman dijalankan ulang.
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
FILES=/srv/jarvis-files
CONFIG=/var/lib/openjarvis/config.toml

if ! id jarvis >/dev/null 2>&1 || [ ! -d /opt/jarvis-tools/jarvis_tools ]; then
    echo "jarvis-tools belum terpasang. Pasang dulu: sudo bash ~/jarvis-tools-src/install.sh" >&2
    exit 1
fi
if [ ! -f "$CONFIG" ]; then
    echo "OpenJarvis belum terpasang. Pasang dulu: sudo bash ~/openjarvis-src/install.sh" >&2
    exit 1
fi

echo "1/5 Grup jarvis-files dan folder kerja $FILES ..."
getent group jarvis-files >/dev/null || groupadd --system jarvis-files
usermod -aG jarvis-files jarvis
usermod -aG jarvis-files "$ADMIN"
install -d -o root -g jarvis-files -m 2770 "$FILES"

echo "2/5 Memasang kode jarvis-tools terbaru ..."
install -o "$ADMIN" -g "$ADMIN" -m 644 "$SRC"/jarvis_tools/*.py /opt/jarvis-tools/jarvis_tools/
install -o "$ADMIN" -g "$ADMIN" -m 755 "$SRC"/bin/* /opt/jarvis-tools/bin/

echo "3/5 Membangun excel-mcp-server sebagai $ADMIN ..."
sudo -u "$ADMIN" -H bash "$SRC/excel/build.sh"

echo "4/5 Menyalakan layanan jarvis-excel ..."
install -o root -g root -m 644 "$SRC/systemd/jarvis-excel.service" /etc/systemd/system/jarvis-excel.service
install -d -o root -g root -m 755 /etc/systemd/system/openjarvis.service.d
install -o root -g root -m 644 "$SRC/systemd/openjarvis-excel.conf" \
    /etc/systemd/system/openjarvis.service.d/excel.conf
systemctl daemon-reload
systemctl enable jarvis-excel.service >/dev/null 2>&1
systemctl restart jarvis-excel.service
sleep 4
if ! systemctl is-active --quiet jarvis-excel.service; then
    journalctl -u jarvis-excel -n 20 --no-pager -o cat
    echo "Layanan Excel gagal menyala. Salin pesan di atas ke Claude." >&2
    exit 1
fi

echo "5/5 Menyambungkan tool Excel ke OpenJarvis ..."
python3 - "$CONFIG" <<'PY'
import json
import os
import re
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    text = fh.read()
match = re.search(r"^servers = '(.*)'$", text, flags=re.M)
if not match:
    sys.exit("Baris 'servers' di [tools.mcp] tidak ditemukan di " + path)
servers = json.loads(match.group(1))
if any(server.get("name") == "excel" for server in servers):
    print("Tool Excel sudah tercatat di konfigurasi OpenJarvis.")
    sys.exit(0)
servers.append({"name": "excel", "url": "http://127.0.0.1:8017/mcp"})
text = text[: match.start()] + "servers = '" + json.dumps(servers) + "'" + text[match.end():]
info = os.stat(path)
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    fh.write(text)
os.chown(tmp, info.st_uid, info.st_gid)
os.chmod(tmp, info.st_mode & 0o777)
os.replace(tmp, path)
print("Tool Excel ditambahkan ke konfigurasi OpenJarvis.")
PY
systemctl restart openjarvis.service
sleep 15
echo "Layanan OpenJarvis: $(systemctl is-active openjarvis.service)"
echo "Layanan Excel: $(systemctl is-active jarvis-excel.service)"
echo
echo "Selesai. Coba di Telegram, misalnya:"
echo "  Buat file Excel anggaran.xlsx berisi pengeluaran bulan ini, lalu kirim ke saya."
