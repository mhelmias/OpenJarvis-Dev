#!/usr/bin/env python3
"""Kirim pengingat yang sudah jatuh tempo ke Telegram.

Dijalankan systemd setiap menit. Pengingat ditandai terkirim hanya setelah
Telegram menerimanya: tidak ada yang terkirim dua kali, dan yang gagal dicoba
lagi pada menit berikutnya.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import store
import telegram_api
from timeparse import format_wib

ENV_PATH = "/etc/jarvis-tools/telegram.env"


def load_env(path: str) -> dict:
    values = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def _duration_text(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} menit"
    hours, rest = divmod(minutes, 60)
    if hours < 48:
        return f"{hours} jam {rest} menit" if rest else f"{hours} jam"
    return f"{hours // 24} hari"


def reminder_text(row, now: datetime) -> str:
    due = store.parse_utc(row["due_at"])
    text = f"⏰ Pengingat: {row['title']}\n{format_wib(due)}"
    late = now - due
    if late > timedelta(minutes=5):
        text += f"\n(terlambat {_duration_text(int(late.total_seconds() // 60))})"
    return text


def run(conn, now: datetime, send) -> tuple[int, int]:
    """Kirim semua pengingat yang jatuh tempo. Kembalikan (terkirim, gagal)."""
    sent = failed = 0
    for row in store.due_unsent(conn, now):
        try:
            send(reminder_text(row, now))
        except Exception as exc:
            failed += 1
            print(f"Gagal mengirim pengingat #{row['id']}: {exc}", file=sys.stderr)
            break  # kemungkinan jaringan atau Telegram bermasalah; coba lagi menit berikutnya
        store.mark_sent(conn, row["id"], now)
        sent += 1
    return sent, failed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Kirim pengingat yang jatuh tempo ke Telegram.")
    parser.add_argument("--test", action="store_true", help="kirim pesan uji lalu keluar")
    args = parser.parse_args(argv)

    env_path = os.environ.get("JARVIS_TOOLS_TELEGRAM_ENV", ENV_PATH)
    try:
        env = load_env(env_path)
        token = env["TELEGRAM_BOT_TOKEN"]
        chat_id = env["TELEGRAM_CHAT_ID"]
    except (OSError, KeyError):
        token = chat_id = None

    def send(text: str) -> None:
        telegram_api.send_message(token, chat_id, text)

    if args.test:
        if not token:
            print(f"Telegram belum diatur ({env_path}). Jalankan: sudo jarvis-telegram-setup")
            return 1
        send("Tes dari jarvis-tools: pengiriman pengingat ke Telegram berjalan.")
        print("Pesan uji terkirim.")
        return 0

    conn = store.connect()
    now = datetime.now(timezone.utc)
    if not token:
        waiting = len(store.due_unsent(conn, now))
        if waiting:
            print(f"{waiting} pengingat menunggu, tetapi Telegram belum diatur. "
                  "Jalankan: sudo jarvis-telegram-setup", file=sys.stderr)
        return 0
    sent, failed = run(conn, now, send)
    if sent or failed:
        print(f"Terkirim {sent}, gagal {failed}.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
