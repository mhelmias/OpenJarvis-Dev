"""Lokasi file dan batas waktu. Bisa diganti lewat environment (dipakai di tes)."""

from __future__ import annotations

import os

STATE_DIR = os.environ.get("JARVIS_PANEL_STATE", "/var/lib/jarvis-ssh")
DB_PATH = os.path.join(STATE_DIR, "panel.db")
SSH_DIR = os.path.join(STATE_DIR, "ssh")
SSH_KEY = os.path.join(SSH_DIR, "id_ed25519")
KNOWN_HOSTS = os.path.join(SSH_DIR, "known_hosts")
# Permintaan ke pembantu root (ganti model, kunci API) dan hasilnya.
SPOOL_DIR = os.path.join(STATE_DIR, "spool")
# API OpenJarvis di server yang sama, untuk daftar tool.
OPENJARVIS_API = os.environ.get("JARVIS_PANEL_OPENJARVIS_API", "http://127.0.0.1:8000").rstrip("/")

# Alamat panel yang dicantumkan di pesan Telegram, misalnya http://100.x.y.z:8020
PANEL_URL = os.environ.get("JARVIS_PANEL_URL", "http://127.0.0.1:8020").rstrip("/")


def telegram_env_path() -> str:
    """systemd memberi salinan telegram.env lewat LoadCredential (CREDENTIALS_DIRECTORY)."""
    explicit = os.environ.get("JARVIS_PANEL_TELEGRAM_ENV")
    if explicit:
        return explicit
    creds = os.environ.get("CREDENTIALS_DIRECTORY")
    if creds:
        return os.path.join(creds, "telegram")
    return "/etc/jarvis-tools/telegram.env"


# OpenJarvis memutus panggilan tool HTTP setelah 60 detik, jadi perintah otomatis
# dibatasi di bawah itu. Perintah yang disetujui dijalankan di luar panggilan tool.
AUTO_TIMEOUT = 40
APPROVED_TIMEOUT = 300
PENDING_MINUTES = 30
MAX_OUTPUT = 16000
SESSION_DAYS = 7
