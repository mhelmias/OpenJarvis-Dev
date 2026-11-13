"""Alur permintaan perintah, dipakai bersama oleh server MCP dan panel web."""

from __future__ import annotations

import logging
import threading

from . import config, db, notify, policy, sshexec

logger = logging.getLogger(__name__)


def servers_text(conn) -> str:
    rows = db.list_servers(conn)
    if not rows:
        return "Belum ada server. Pemilik bisa menambahkannya di panel."
    lines = ["Server yang bisa dikelola:"]
    for row in rows:
        note = f" — {row['note']}" if row["note"] else ""
        lines.append(f"- {row['name']}: {row['username']}@{row['host']}, mode {row['mode']} "
                     f"({policy.MODES.get(row['mode'], row['mode'])}){note}")
    return "\n".join(lines)


def approval_message(request_id: int, server, command: str, reason: str) -> str:
    return (
        f"🔐 Persetujuan dibutuhkan (#{request_id})\n"
        f"Server: {server['name']} ({server['username']}@{server['host']})\n"
        f"Perintah: {command}\n"
        f"Alasan AI: {reason or '-'}\n"
        f"Buka panel: {config.PANEL_URL}/permintaan/{request_id}"
    )


def submit(conn, server, command: str, reason: str) -> tuple[str, bool]:
    """Tangani satu permintaan dari AI. Kembalikan (teks untuk AI, apakah error)."""
    command = (command or "").strip()
    decision = policy.classify(command, server["mode"], server["allow_patterns"])
    if decision.kind == "refused":
        rid = db.create_request(conn, server, command, reason, "refused", "refused", decision.reason)
        return f"Ditolak (#{rid}): {decision.reason}", True
    if decision.kind == "auto":
        rid = db.create_request(conn, server, command, reason, "auto", "running", decision.reason)
        code, output = sshexec.run(server, command, config.AUTO_TIMEOUT)
        db.finish_request(conn, rid, code, output)
        return (
            f"Perintah #{rid} di server {server['name']} selesai, kode keluar {code}.\n"
            f"{output.strip() or '(tanpa keluaran)'}"
        ), False
    rid = db.create_request(conn, server, command, reason, "approval", "pending", decision.reason)
    sent = notify.send(approval_message(rid, server, command, reason))
    where = "Pemberitahuan sudah dikirim ke Telegram pemilik." if sent else (
        "Pemberitahuan Telegram gagal dikirim, jadi pemilik perlu membuka panel sendiri.")
    return (
        f"Perintah #{rid} belum dijalankan: {decision.reason} {where} "
        f"Setelah disetujui di panel, perintah dijalankan dan hasilnya dikirim ke Telegram pemilik. "
        f"Batas waktu persetujuan {config.PENDING_MINUTES} menit. Hasilnya juga bisa dilihat dengan ssh_request."
    ), False


def request_text(row) -> str:
    status = db.STATUS_TEXT.get(row["status"], row["status"])
    text = f"Perintah #{row['id']} di server {row['server_name']}: {status}.\n$ {row['command']}"
    if row["status"] in ("done", "failed"):
        text += f"\nKode keluar {row['exit_code']}.\n{(row['output'] or '').strip() or '(tanpa keluaran)'}"
    elif row["note"]:
        text += f"\nKeterangan: {row['note']}"
    return text


def _run_approved(request_id: int) -> None:
    conn = db.connect()
    try:
        row = db.get_request(conn, request_id)
        server = db.get_server(conn, row["server_id"]) if row else None
        if row is None:
            return
        if server is None:
            db.finish_request(conn, request_id, 255, "Server sudah dihapus dari panel.")
            return
        code, output = sshexec.run(server, row["command"], config.APPROVED_TIMEOUT)
        db.finish_request(conn, request_id, code, output)
        icon = "✅" if code == 0 else "⚠️"
        notify.send(
            f"{icon} Perintah #{request_id} di {server['name']} sudah dijalankan, kode keluar {code}.\n"
            f"$ {row['command']}\n{output.strip() or '(tanpa keluaran)'}"
        )
    except Exception:
        logger.exception("Gagal menjalankan perintah #%s", request_id)
        try:
            db.finish_request(conn, request_id, 255, "Terjadi kesalahan di panel saat menjalankan perintah.")
        except Exception:
            logger.exception("Gagal mencatat kegagalan #%s", request_id)
    finally:
        conn.close()


def run_approved_async(request_id: int) -> threading.Thread:
    thread = threading.Thread(target=_run_approved, args=(request_id,), daemon=True,
                              name=f"jarvis-panel-run-{request_id}")
    thread.start()
    return thread


def notify_denied(row) -> None:
    notify.send(f"⛔ Perintah #{row['id']} di {row['server_name']} ditolak, tidak dijalankan.\n$ {row['command']}")
