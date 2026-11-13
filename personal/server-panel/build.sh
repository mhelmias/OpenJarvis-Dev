#!/usr/bin/env bash
# Pasang atau perbarui kode Jarvis Panel di /opt/jarvis-tools/panel, tanpa sudo:
#   bash ~/jarvis-panel-src/build.sh
# Setelah memperbarui: sudo systemctl restart jarvis-panel-web jarvis-panel-mcp
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="${BASE:-/opt/jarvis-tools/panel}"

export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
    echo "uv belum ada. Pasang OpenJarvis dulu: sudo bash ~/openjarvis-src/install.sh" >&2
    exit 1
fi
export UV_PYTHON_INSTALL_DIR=/opt/jarvis-tools/python
export UV_PYTHON_PREFERENCE=only-managed
export UV_LINK_MODE=copy

mkdir -p "$BASE"
rsync -a --delete --exclude '__pycache__' "$HERE/jarvis_panel/" "$BASE/jarvis_panel/"
if [ ! -x "$BASE/venv/bin/python" ]; then
    uv venv --quiet --python 3.13 "$BASE/venv"
fi
uv pip sync --quiet --python "$BASE/venv/bin/python" --require-hashes "$HERE/requirements.lock"
(cd "$BASE" && "$BASE/venv/bin/python" -c "import jarvis_panel.web_app, jarvis_panel.mcp_app")
echo "Jarvis Panel siap di $BASE"
