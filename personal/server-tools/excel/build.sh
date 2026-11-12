#!/usr/bin/env bash
# Bangun atau perbarui excel-mcp-server di /opt/jarvis-tools/excel, tanpa sudo:
#   bash ~/jarvis-tools-src/excel/build.sh
# Paket dipasang persis sesuai requirements.lock (dengan hash).
# Setelah memperbarui, jalankan ulang layanannya: sudo systemctl restart jarvis-excel
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="${BASE:-/opt/jarvis-tools/excel}"

export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
    echo "uv belum ada. Pasang OpenJarvis dulu: sudo bash ~/openjarvis-src/install.sh" >&2
    exit 1
fi
# Python khusus untuk tool ini, di /opt supaya bisa dibaca akun jarvis.
export UV_PYTHON_INSTALL_DIR=/opt/jarvis-tools/python
export UV_PYTHON_PREFERENCE=only-managed
export UV_LINK_MODE=copy

mkdir -p "$BASE"
if [ ! -x "$BASE/venv/bin/python" ]; then
    uv venv --quiet --python 3.13 "$BASE/venv"
fi
uv pip sync --quiet --python "$BASE/venv/bin/python" --require-hashes "$HERE/requirements.lock"
"$BASE/venv/bin/excel-mcp-server" --help >/dev/null
VERSION="$("$BASE/venv/bin/python" -c 'import importlib.metadata as m; print(m.version("excel-mcp-server"))')"
echo "excel-mcp-server $VERSION siap di $BASE/venv"
