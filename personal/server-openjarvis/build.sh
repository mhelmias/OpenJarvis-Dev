#!/usr/bin/env bash
# Bangun atau perbarui OpenJarvis di /opt/openjarvis, tanpa sudo:
#   bash ~/openjarvis-src/build.sh
# Setelah memperbarui, jalankan ulang layanan: sudo systemctl restart openjarvis
set -euo pipefail

BASE="${BASE:-/opt/openjarvis}"
REPO_URL="${REPO_URL:-https://github.com/mhelmias/OpenJarvis-Dev.git}"
BRANCH="${BRANCH:-main}"
# Tambalan pribadi untuk kode inti (lihat patches/README.md), dipasang setiap build.
PATCHES="$(cd "$(dirname "$0")" && pwd)/patches"

if [ ! -w "$BASE" ]; then
    echo "$BASE belum ada. Jalankan dulu: sudo bash ~/openjarvis-src/install.sh" >&2
    exit 1
fi
exec > >(tee -a "$BASE/build.log") 2>&1
echo "== build $(date -Is) =="

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
    echo "Memasang uv (pengelola Python) ke ~/.local/bin ..."
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
fi
# Modul Rust OpenJarvis (pengaman, loop guard, memori) dibangun dari kode sumber.
if ! command -v cc >/dev/null 2>&1 || ! command -v cmake >/dev/null 2>&1; then
    echo "Compiler C atau cmake belum ada. Jalankan: sudo bash ~/openjarvis-src/install.sh" >&2
    exit 1
fi
if ! command -v rustup >/dev/null 2>&1; then
    echo "Memasang Rust (rustup) ke ~/.cargo ..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --profile minimal --default-toolchain none --no-modify-path
fi

if [ -d "$BASE/src/.git" ]; then
    echo "Memperbarui kode OpenJarvis ..."
    # Buang tambalan lama dulu; tambalan dipasang ulang setelah kode diperbarui.
    git -C "$BASE/src" checkout --quiet -- .
    git -C "$BASE/src" fetch --quiet origin "$BRANCH"
    git -C "$BASE/src" checkout --quiet "$BRANCH"
    git -C "$BASE/src" merge --ff-only --quiet "origin/$BRANCH"
else
    echo "Mengunduh kode OpenJarvis ..."
    git clone --quiet --branch "$BRANCH" "$REPO_URL" "$BASE/src"
fi
echo "Versi kode: $(git -C "$BASE/src" log -1 --format='%h %s')"
for patch in "$PATCHES"/*.patch; do
    [ -e "$patch" ] || continue
    echo "Memasang tambalan $(basename "$patch") ..."
    if ! git -C "$BASE/src" apply "$patch"; then
        echo "Tambalan $(basename "$patch") tidak cocok lagi dengan kode terbaru. Perbarui patch-nya dulu." >&2
        exit 1
    fi
done

RUST_CHANNEL="$(sed -n 's/^channel *= *"\(.*\)"/\1/p' "$BASE/src/rust/rust-toolchain.toml")"
echo "Menyiapkan Rust $RUST_CHANNEL ..."
rustup toolchain install "$RUST_CHANNEL" --profile minimal -c rustfmt -c clippy

# Python dan venv diletakkan di /opt supaya bisa dibaca akun jarvis.
export UV_PYTHON_INSTALL_DIR="$BASE/python"
export UV_PROJECT_ENVIRONMENT="$BASE/venv"
export UV_PYTHON_PREFERENCE=only-managed
export UV_LINK_MODE=copy
cd "$BASE/src"
echo "Memasang paket Python dan membangun modul Rust (bisa 10-20 menit, layar tampak diam) ..."
uv sync --frozen --python 3.13 --extra server --group desktop-native --no-dev

"$BASE/venv/bin/jarvis" --help >/dev/null
"$BASE/venv/bin/python" -c "import openjarvis_rust"
echo "OpenJarvis dan modul Rust siap di $BASE/venv"
