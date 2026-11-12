"""Pemanggil Bot API Telegram sederhana, tanpa pustaka tambahan.

Pesan kesalahan sengaja tidak memuat URL, karena URL Bot API berisi token.
"""

from __future__ import annotations

import json
import mimetypes
import secrets
import urllib.error
import urllib.request

API = "https://api.telegram.org"


class TelegramError(Exception):
    pass


def _post(token: str, method: str, data: bytes, content_type: str, timeout: float):
    request = urllib.request.Request(
        f"{API}/bot{token}/{method}",
        data=data,
        headers={"Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            body = json.load(exc)
        except Exception:
            raise TelegramError(f"HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise TelegramError(f"Tidak bisa menghubungi Telegram: {reason}") from None
    if not body.get("ok"):
        raise TelegramError(body.get("description") or "Telegram menolak permintaan")
    return body.get("result")


def call(token: str, method: str, payload: dict | None = None, timeout: float = 15):
    data = json.dumps(payload or {}).encode("utf-8")
    return _post(token, method, data, "application/json", timeout)


def send_message(token: str, chat_id, text: str):
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    return call(token, "sendMessage", payload)


def get_me(token: str):
    return call(token, "getMe")


def get_updates(token: str):
    return call(token, "getUpdates", {"timeout": 0, "allowed_updates": ["message"]})


def multipart(fields: dict, file_field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    """Susun body multipart/form-data. Kembalikan (body, content type)."""
    boundary = "jarvis-" + secrets.token_hex(16)
    safe_name = filename.replace('"', "'").replace("\r", " ").replace("\n", " ")
    file_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    parts = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{safe_name}"\r\nContent-Type: {file_type}\r\n\r\n'.encode("utf-8")
        + data
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def send_document(token: str, chat_id, filename: str, data: bytes, caption: str = ""):
    fields = {"chat_id": str(chat_id)}
    if caption:
        fields["caption"] = caption
    body, content_type = multipart(fields, "document", filename, data)
    return _post(token, "sendDocument", body, content_type, timeout=120)
