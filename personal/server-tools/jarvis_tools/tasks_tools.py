"""Tool pengingat tugas yang dipanggil OpenJarvis lewat MCP."""

from __future__ import annotations

from datetime import datetime

import store
from timeparse import WhenError, format_wib, parse_when

_WHEN_HELP = (
    "Frasa waktu persis seperti yang ditulis pengguna, misalnya 'besok jam 9 pagi', "
    "'30 menit lagi', atau 'Jumat jam 2 siang'. Jangan diubah menjadi tanggal; "
    "server yang menghitungnya."
)
_TASK_ID = {"type": "integer", "description": "Nomor tugas, misalnya 3 untuk tugas #3."}

TOOLS = [
    {
        "name": "add_reminder",
        "description": (
            "Simpan tugas baru beserta waktu pengingatnya. Pengingat dikirim ke Telegram "
            "pemilik saat waktunya tiba. Kalau pengguna belum menyebut waktunya, tanyakan dulu. "
            "Sampaikan ke pengguna tanggal dan jam yang dikembalikan tool ini."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Judul singkat tugas, misalnya 'Bayar listrik'.",
                },
                "when": {"type": "string", "description": _WHEN_HELP},
            },
            "required": ["title", "when"],
        },
    },
    {
        "name": "list_tasks",
        "description": (
            "Tampilkan daftar tugas beserta nomor dan waktu pengingatnya. "
            "Hasilnya juga memuat tanggal dan jam saat ini."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["open", "done", "all"],
                    "description": "open = belum selesai (bawaan), done = sudah selesai, all = semua.",
                },
            },
        },
    },
    {
        "name": "complete_task",
        "description": (
            "Tandai tugas sudah selesai berdasarkan nomornya. "
            "Kalau nomornya belum diketahui, panggil list_tasks dulu."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": _TASK_ID},
            "required": ["task_id"],
        },
    },
    {
        "name": "snooze_task",
        "description": (
            "Ubah atau tunda waktu pengingat sebuah tugas berdasarkan nomornya. "
            "Kalau nomornya belum diketahui, panggil list_tasks dulu."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": _TASK_ID,
                "when": {"type": "string", "description": _WHEN_HELP},
            },
            "required": ["task_id", "when"],
        },
    },
]


class ToolError(Exception):
    """Kesalahan yang pesannya aman ditunjukkan ke pengguna."""


def call_tool(name: str, args: dict, conn, now: datetime) -> tuple[str, bool]:
    """Jalankan tool. Kembalikan (teks hasil, apakah error)."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Tool tidak dikenal: {name}", True
    try:
        return handler(conn, args or {}, now), False
    except (ToolError, WhenError) as exc:
        return str(exc), True


def _title(args: dict) -> str:
    title = str(args.get("title") or "").strip()
    if not title:
        raise ToolError("Judul tugas kosong. Apa nama tugasnya?")
    if len(title) > 200:
        raise ToolError("Judul tugas terlalu panjang (maksimal 200 karakter).")
    return title


def _task_id(args: dict) -> int:
    try:
        return int(str(args.get("task_id")).strip().lstrip("#"))
    except (TypeError, ValueError):
        raise ToolError(
            "Nomor tugas tidak valid. Panggil list_tasks untuk melihat nomornya."
        ) from None


def _existing_task(conn, task_id: int):
    row = store.get_task(conn, task_id)
    if row is None:
        raise ToolError(
            f"Tugas #{task_id} tidak ditemukan. Panggil list_tasks untuk melihat nomornya."
        )
    return row


def _describe(row) -> str:
    due = format_wib(store.parse_utc(row["due_at"]))
    if row["status"] == "done":
        return f"#{row['id']} {row['title']} (selesai), pengingat {due}"
    note = " (pengingat sudah dikirim)" if row["sent_at"] else ""
    return f"#{row['id']} {row['title']}, pengingat {due}{note}"


def _add_reminder(conn, args: dict, now: datetime) -> str:
    title = _title(args)
    when = str(args.get("when") or "").strip()
    due = parse_when(when, now)
    task_id = store.add_task(conn, title, due, when, now)
    return f"Tersimpan sebagai tugas #{task_id}: {title}. Pengingat dikirim {format_wib(due)}."


def _list_tasks(conn, args: dict, now: datetime) -> str:
    status = str(args.get("status") or "open").strip().lower()
    if status not in ("open", "done", "all"):
        status = "open"
    label = {"open": "belum selesai", "done": "sudah selesai", "all": "semua"}[status]
    rows = store.list_tasks(conn, status)
    header = f"Sekarang: {format_wib(now)}."
    if not rows:
        return f"{header}\nTidak ada tugas {label}."
    lines = [header, f"Tugas {label} ({len(rows)}):"]
    lines.extend(_describe(row) for row in rows)
    return "\n".join(lines)


def _complete_task(conn, args: dict, now: datetime) -> str:
    task_id = _task_id(args)
    row = _existing_task(conn, task_id)
    if row["status"] == "done":
        return f"Tugas #{task_id} ({row['title']}) memang sudah selesai."
    store.complete_task(conn, task_id, now)
    return f"Tugas #{task_id} ({row['title']}) ditandai selesai."


def _snooze_task(conn, args: dict, now: datetime) -> str:
    task_id = _task_id(args)
    row = _existing_task(conn, task_id)
    when = str(args.get("when") or "").strip()
    due = parse_when(when, now)
    store.reschedule_task(conn, task_id, due, when)
    return f"Pengingat tugas #{task_id} ({row['title']}) dipindah ke {format_wib(due)}."


_HANDLERS = {
    "add_reminder": _add_reminder,
    "list_tasks": _list_tasks,
    "complete_task": _complete_task,
    "snooze_task": _snooze_task,
}
