#!/usr/bin/env python3
"""Atur bot Telegram untuk pengingat. Jalankan dengan: sudo jarvis-telegram-setup

Token diketik langsung di terminal (tidak terlihat) dan disimpan di
/etc/jarvis-tools/telegram.env, yang hanya bisa dibaca root dan akun jarvis.
"""

from __future__ import annotations

import getpass
import grp
import os
import re
import sys
import tempfile

import telegram_api

ENV_PATH = "/etc/jarvis-tools/telegram.env"
TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")


def find_private_chat(updates) -> dict | None:
    for update in reversed(updates or []):
        chat = (update.get("message") or {}).get("chat") or {}
        if chat.get("type") == "private":
            return chat
    return None


def save_env(token: str, chat_id) -> None:
    folder = os.path.dirname(ENV_PATH)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(f"TELEGRAM_BOT_TOKEN={token}\nTELEGRAM_CHAT_ID={chat_id}\n")
    os.chown(tmp, 0, grp.getgrnam("jarvis").gr_gid)
    os.chmod(tmp, 0o640)
    os.replace(tmp, ENV_PATH)


def main() -> int:
    if os.geteuid() != 0:
        print("Jalankan dengan sudo: sudo jarvis-telegram-setup")
        return 1
    print("Token bot didapat dari @BotFather. Token tidak terlihat saat ditempel atau diketik.")
    token = getpass.getpass("Token bot Telegram: ").strip()
    if not TOKEN_RE.match(token):
        print("Bentuk token tidak sesuai. Token berbentuk angka:huruf, misalnya 123456789:AAH...")
        return 1
    try:
        me = telegram_api.get_me(token)
    except telegram_api.TelegramError as exc:
        print(f"Token ditolak Telegram: {exc}")
        return 1
    username = me.get("username") or "bot Anda"
    print(f"Bot ditemukan: @{username}")

    chat = None
    for _ in range(5):
        try:
            chat = find_private_chat(telegram_api.get_updates(token))
        except telegram_api.TelegramError as exc:
            print(f"Gagal membaca pesan ke bot: {exc}")
            return 1
        if chat:
            break
        input(f"Buka @{username} di Telegram, tekan Start atau kirim pesan apa saja, "
              "lalu tekan Enter di sini... ")
    if not chat:
        print("Belum ada pesan ke bot. Jalankan lagi perintah ini setelah menekan Start.")
        return 1
    name = chat.get("first_name") or chat.get("username") or "Anda"
    print(f"Chat ditemukan: {name}")

    save_env(token, chat["id"])
    try:
        telegram_api.send_message(
            token, chat["id"], "Halo! Pengingat dari server sudah tersambung ke Telegram ini."
        )
    except telegram_api.TelegramError as exc:
        print(f"Pengaturan tersimpan, tetapi pesan uji gagal: {exc}")
        return 1
    print("Selesai. Pesan uji sudah dikirim ke Telegram Anda.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
