"""Tool file yang dipanggil OpenJarvis lewat MCP.

Folder kerja Jarvis (/srv/jarvis-files) juga dipakai tool Excel. Tool di sini hanya
membaca folder itu: menampilkan isinya dan mengirim file ke Telegram pemilik.
"""

from __future__ import annotations

import os
from datetime import datetime

import send_due
import telegram_api
from timeparse import WIB

FILES_ROOT = os.environ.get("JARVIS_FILES_ROOT", "/srv/jarvis-files")
MAX_SEND_BYTES = 50 * 1024 * 1024  # batas unggah Bot API Telegram
MAX_LIST = 200
MAX_CAPTION = 1000

TOOLS = [
    {
        "name": "list_files",
        "description": (
            "Tampilkan file di folder kerja Jarvis, tempat file Excel dibuat dan disimpan. "
            "Nama yang ditampilkan bisa langsung dipakai di send_file dan tool Excel."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder": {
                    "type": "string",
                    "description": "Subfolder (opsional), misalnya 'laporan'. Kosongkan untuk semua file.",
                },
            },
        },
    },
    {
        "name": "send_file",
        "description": (
            "Kirim satu file dari folder kerja Jarvis ke Telegram pemilik sebagai dokumen. "
            "Pakai setelah membuat atau mengubah file kalau pengguna ingin menerimanya."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Nama file di folder kerja, misalnya 'anggaran.xlsx' atau 'laporan/q1.xlsx'.",
                },
                "caption": {"type": "string", "description": "Keterangan singkat (opsional)."},
            },
            "required": ["path"],
        },
    },
]
NAMES = {tool["name"] for tool in TOOLS}

# Bisa diganti di tes supaya tidak benar-benar mengirim ke Telegram.
_send_document = telegram_api.send_document


class ToolError(Exception):
    """Kesalahan yang pesannya aman ditunjukkan ke pengguna."""


def call_tool(name: str, args: dict) -> tuple[str, bool]:
    """Jalankan tool. Kembalikan (teks hasil, apakah error)."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Tool tidak dikenal: {name}", True
    try:
        return handler(args or {}), False
    except ToolError as exc:
        return str(exc), True
    except telegram_api.TelegramError as exc:
        return f"Gagal mengirim ke Telegram: {exc}", True


def _root() -> str:
    return os.path.realpath(FILES_ROOT)


def _resolve(raw) -> str:
    """Ubah nama dari pengguna menjadi path asli yang dijamin ada di dalam folder kerja."""
    text = str(raw or "").strip()
    if not text:
        raise ToolError("Nama file belum diisi.")
    root = _root()
    real = os.path.realpath(text if os.path.isabs(text) else os.path.join(root, text))
    if real != root and not real.startswith(root + os.sep):
        raise ToolError("File harus berada di folder kerja Jarvis.")
    return real


def _size_text(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB".replace(".", ",")


def _time_text(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, WIB).strftime("%d-%m-%Y %H.%M WIB")


def _list_files(args: dict) -> str:
    root = _root()
    base = _resolve(args["folder"]) if str(args.get("folder") or "").strip() else root
    if not os.path.isdir(base):
        raise ToolError("Folder tidak ditemukan di folder kerja.")
    entries = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(name for name in dirnames if not name.startswith("."))
        for name in sorted(filenames):
            if name.startswith((".", "~$")):
                continue
            full = os.path.join(dirpath, name)
            try:
                info = os.stat(full)
            except OSError:
                continue
            entries.append((os.path.relpath(full, root), info.st_size, info.st_mtime))
        if len(entries) >= MAX_LIST:
            break
    if not entries:
        return "Folder kerja masih kosong."
    lines = [f"File di folder kerja ({min(len(entries), MAX_LIST)}):"]
    for rel, size, mtime in entries[:MAX_LIST]:
        lines.append(f"- {rel} ({_size_text(size)}, diubah {_time_text(mtime)})")
    if len(entries) > MAX_LIST:
        lines.append(f"(hanya {MAX_LIST} file pertama yang ditampilkan)")
    return "\n".join(lines)


def _telegram_target() -> tuple[str, str]:
    path = os.environ.get("JARVIS_TOOLS_TELEGRAM_ENV", send_due.ENV_PATH)
    try:
        env = send_due.load_env(path)
        return env["TELEGRAM_BOT_TOKEN"], env["TELEGRAM_CHAT_ID"]
    except (OSError, KeyError):
        raise ToolError("Telegram belum diatur di server, jadi file belum bisa dikirim.") from None


def _send_file(args: dict) -> str:
    path = _resolve(args.get("path"))
    if not os.path.isfile(path):
        raise ToolError("File tidak ditemukan. Panggil list_files untuk melihat nama yang ada.")
    size = os.path.getsize(path)
    if size > MAX_SEND_BYTES:
        raise ToolError("File lebih dari 50 MB, terlalu besar untuk dikirim lewat Telegram.")
    caption = str(args.get("caption") or "").strip()[:MAX_CAPTION]
    token, chat_id = _telegram_target()
    with open(path, "rb") as fh:
        data = fh.read()
    _send_document(token, chat_id, os.path.basename(path), data, caption)
    rel = os.path.relpath(path, _root())
    return f"File {rel} ({_size_text(size)}) sudah terkirim ke Telegram pemilik."


_HANDLERS = {
    "list_files": _list_files,
    "send_file": _send_file,
}
