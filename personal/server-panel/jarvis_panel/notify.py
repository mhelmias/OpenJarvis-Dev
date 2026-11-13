"""Pemberitahuan ke Telegram pemilik (bot yang sama dengan pengingat). Gagal kirim tidak fatal."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from . import config

logger = logging.getLogger(__name__)
_MAX = 3800  # batas pesan Telegram 4096 karakter


def _load_env(path: str) -> dict:
    values = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
    return values


def send(text: str) -> bool:
    try:
        env = _load_env(config.telegram_env_path())
        token, chat_id = env["TELEGRAM_BOT_TOKEN"], env["TELEGRAM_CHAT_ID"]
    except (OSError, KeyError):
        logger.warning("Telegram belum diatur; pemberitahuan tidak dikirim")
        return False
    if len(text) > _MAX:
        text = text[:_MAX] + "\n... (dipotong; lihat panel)"
    payload = json.dumps({"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return bool(json.load(resp).get("ok"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # Jangan cetak URL: berisi token.
        logger.warning("Gagal mengirim pemberitahuan Telegram: %s", type(exc).__name__)
        return False
