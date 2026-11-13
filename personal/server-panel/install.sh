#!/usr/bin/env bash
# Pasang Jarvis Panel: halaman web pengelola server + tool SSH untuk OpenJarvis.
# Jalankan dari akun admin:
#   sudo bash ~/jarvis-panel-src/install.sh
# Aman dijalankan ulang: database, kata sandi panel, dan kunci SSH yang sudah ada tidak ditimpa.
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
PANEL=/opt/jarvis-tools/panel
STATE=/var/lib/jarvis-ssh
PY="$PANEL/venv/bin/python"
CONFIG=/var/lib/openjarvis/config.toml

if [ ! -d /opt/jarvis-tools ] || [ ! -f /etc/jarvis-tools/telegram.env ]; then
    echo "jarvis-tools dan Telegram belum terpasang. Pasang dulu: sudo bash ~/jarvis-tools-src/install.sh" >&2
    exit 1
fi
if [ ! -f "$CONFIG" ]; then
    echo "OpenJarvis belum terpasang. Pasang dulu: sudo bash ~/openjarvis-src/install.sh" >&2
    exit 1
fi
TS_IP="$(tailscale ip -4 2>/dev/null | head -n 1 || true)"
if ! [[ "$TS_IP" =~ ^100\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Alamat Tailscale server tidak ditemukan. Pastikan Tailscale menyala." >&2
    exit 1
fi

echo "1/6 Akun jarvis-ssh (panel) dan jarvis-ops (akun AI di server ini, tanpa sudo) ..."
if ! id jarvis-ssh >/dev/null 2>&1; then
    useradd --system --home-dir "$STATE" --create-home --shell /usr/sbin/nologin \
        --comment "Jarvis Panel" jarvis-ssh
fi
chown jarvis-ssh:jarvis-ssh "$STATE"
chmod 700 "$STATE"
if ! id jarvis-ops >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash --comment "Akun AI untuk perintah server, tanpa sudo" jarvis-ops
    usermod --password '*' jarvis-ops
fi
# Boleh membaca log sistem, tidak boleh sudo atau docker.
usermod -aG adm,systemd-journal jarvis-ops

echo "2/6 Membangun Jarvis Panel sebagai $ADMIN ..."
sudo -u "$ADMIN" -H bash "$SRC/build.sh"

echo "3/6 Menyiapkan database, kunci SSH panel, dan kata sandi panel ..."
install -d -o root -g root -m 755 /etc/jarvis-ssh
printf 'JARVIS_PANEL_HOST=%s\nJARVIS_PANEL_URL=http://%s:8020\n' "$TS_IP" "$TS_IP" > /etc/jarvis-ssh/panel.env
chmod 644 /etc/jarvis-ssh/panel.env
cat > /usr/local/sbin/jarvis-panel-setup <<'EOF'
#!/bin/sh
# Siapkan Jarvis Panel, atau ganti kata sandinya: sudo jarvis-panel-setup --password
cd /opt/jarvis-tools/panel || exit 1
exec runuser -u jarvis-ssh -- env JARVIS_PANEL_STATE=/var/lib/jarvis-ssh HOME=/var/lib/jarvis-ssh \
    /opt/jarvis-tools/panel/venv/bin/python -m jarvis_panel setup "$@"
EOF
chmod 755 /usr/local/sbin/jarvis-panel-setup
/usr/local/sbin/jarvis-panel-setup

run_panel() {
    (cd "$PANEL" && runuser -u jarvis-ssh -- env JARVIS_PANEL_STATE="$STATE" HOME="$STATE" "$PY" -m jarvis_panel "$@")
}
PUBKEY="$(run_panel pubkey)"
TOKEN="$(run_panel token)"

echo "4/6 Mengizinkan kunci panel masuk ke akun jarvis-ops di server ini ..."
OPS_HOME="$(getent passwd jarvis-ops | cut -d: -f6)"
install -d -o jarvis-ops -g jarvis-ops -m 700 "$OPS_HOME/.ssh"
LINE="restrict $PUBKEY"
touch "$OPS_HOME/.ssh/authorized_keys"
grep -qxF "$LINE" "$OPS_HOME/.ssh/authorized_keys" || echo "$LINE" >> "$OPS_HOME/.ssh/authorized_keys"
chown jarvis-ops:jarvis-ops "$OPS_HOME/.ssh/authorized_keys"
chmod 600 "$OPS_HOME/.ssh/authorized_keys"
run_panel add-server ai 127.0.0.1 jarvis-ops --mode setuju --note "server ini (i5-4590S)"
run_panel test ai || echo "Peringatan: tes SSH ke jarvis-ops@127.0.0.1 gagal. Cek pesan di atas."

echo "5/6 Menyalakan layanan panel dan pembantu ganti model ..."
if [ ! -x /usr/local/sbin/jarvis-model ]; then
    echo "jarvis-model belum ada. Pasang OpenJarvis dulu: sudo bash ~/openjarvis-src/install.sh" >&2
    exit 1
fi
install -d -o jarvis-ssh -g jarvis-ssh -m 700 "$STATE/spool"
install -o root -g root -m 755 "$SRC/helper/jarvis-panel-helper" /usr/local/sbin/jarvis-panel-helper
install -o root -g root -m 644 "$SRC/systemd/jarvis-panel-helper.service" /etc/systemd/system/
install -o root -g root -m 644 "$SRC/systemd/jarvis-panel-helper.path" /etc/systemd/system/
install -o root -g root -m 644 "$SRC/systemd/jarvis-panel-web.service" /etc/systemd/system/
install -o root -g root -m 644 "$SRC/systemd/jarvis-panel-mcp.service" /etc/systemd/system/
install -d -o root -g root -m 755 /etc/systemd/system/openjarvis.service.d
install -o root -g root -m 644 "$SRC/systemd/openjarvis-ssh.conf" /etc/systemd/system/openjarvis.service.d/ssh.conf
systemctl daemon-reload
systemctl enable jarvis-panel-web.service jarvis-panel-mcp.service jarvis-panel-helper.path >/dev/null 2>&1
systemctl restart jarvis-panel-web.service jarvis-panel-mcp.service jarvis-panel-helper.path
sleep 4
for unit in jarvis-panel-web jarvis-panel-mcp; do
    if ! systemctl is-active --quiet "$unit"; then
        journalctl -u "$unit" -n 20 --no-pager -o cat
        echo "Layanan $unit gagal menyala. Salin pesan di atas ke Claude." >&2
        exit 1
    fi
done

echo "6/6 Menyambungkan tool SSH ke OpenJarvis ..."
python3 - "$CONFIG" "$TOKEN" <<'PY'
import json
import os
import re
import sys

path, token = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    text = fh.read()
match = re.search(r"^servers = '(.*)'$", text, flags=re.M)
if not match:
    sys.exit("Baris 'servers' di [tools.mcp] tidak ditemukan di " + path)
servers = [s for s in json.loads(match.group(1)) if s.get("name") != "ssh"]
servers.append({"name": "ssh", "url": "http://127.0.0.1:8019/mcp", "token": token})
text = text[: match.start()] + "servers = '" + json.dumps(servers) + "'" + text[match.end():]
info = os.stat(path)
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    fh.write(text)
os.chown(tmp, info.st_uid, info.st_gid)
os.chmod(tmp, info.st_mode & 0o777)
os.replace(tmp, path)
print("Tool SSH tercatat di konfigurasi OpenJarvis.")
PY
systemctl restart openjarvis.service
sleep 15
echo "Layanan OpenJarvis: $(systemctl is-active openjarvis.service)"
echo
echo "Selesai. Buka panel dari laptop atau HP yang tersambung Tailscale:"
echo "  http://$TS_IP:8020"
echo "Lalu coba di Telegram, misalnya: Cek pemakaian disk server ai."
