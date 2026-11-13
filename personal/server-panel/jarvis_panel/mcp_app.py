"""Server MCP (Streamable HTTP, balasan JSON) untuk OpenJarvis.

Hanya mendengarkan di 127.0.0.1 dan mewajibkan token Bearer. Tool-nya sedikit supaya
pesan ke model tetap ringkas.
"""

from __future__ import annotations

import logging
import secrets

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from . import __version__, actions, db, security

logger = logging.getLogger(__name__)

SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
FALLBACK_VERSION = "2025-03-26"

TOOLS = [
    {
        "name": "ssh_servers",
        "description": (
            "Tampilkan server yang boleh dikelola lewat SSH beserta modenya. Mode baca: hanya "
            "perintah baca. Mode setuju: perintah lain menunggu persetujuan pemilik. Mode bebas: "
            "semua langsung jalan. Panggil ini dulu kalau belum tahu nama server."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ssh_run",
        "description": (
            "Jalankan satu perintah shell di server lewat SSH. Perintah yang hanya membaca "
            "(df -h, free -h, uptime, systemctl status, journalctl -n 50 --no-pager, docker ps, "
            "dan sejenisnya) langsung dijalankan dan hasilnya dikembalikan. Perintah yang bisa "
            "mengubah sistem tidak langsung jalan: pemilik diminta menyetujuinya di panel, lalu "
            "hasilnya dikirim ke Telegram pemilik. Kirim satu perintah per panggilan, jangan "
            "dirangkai dengan ; atau &&."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Nama server dari ssh_servers, misalnya 'ai'."},
                "command": {
                    "type": "string",
                    "description": "Perintah shell, misalnya 'df -h' atau 'systemctl status nginx --no-pager'.",
                },
                "reason": {
                    "type": "string",
                    "description": "Alasan singkat (bahasa Indonesia), ditampilkan ke pemilik saat minta persetujuan.",
                },
            },
            "required": ["server", "command"],
        },
    },
    {
        "name": "ssh_request",
        "description": (
            "Lihat status dan hasil perintah sebelumnya berdasarkan nomornya, misalnya setelah "
            "pemilik menyetujui perintah."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "integer", "description": "Nomor perintah, misalnya 12 untuk #12."},
            },
            "required": ["request_id"],
        },
    },
]


def call_tool(name: str, args: dict) -> tuple[str, bool]:
    conn = db.connect()
    try:
        if name == "ssh_servers":
            return actions.servers_text(conn), False
        if name == "ssh_run":
            server_name = str(args.get("server") or "").strip()
            server = db.get_server_by_name(conn, server_name)
            if server is None:
                return "Server tidak dikenal. Panggil ssh_servers untuk melihat nama yang ada.", True
            reason = str(args.get("reason") or "").strip()[:500]
            return actions.submit(conn, server, str(args.get("command") or ""), reason)
        if name == "ssh_request":
            try:
                request_id = int(str(args.get("request_id")).lstrip("#"))
            except (TypeError, ValueError):
                return "Nomor perintah tidak valid.", True
            db.expire_pending(conn)
            row = db.get_request(conn, request_id)
            if row is None:
                return f"Perintah #{request_id} tidak ditemukan.", True
            return actions.request_text(row), False
        return f"Tool tidak dikenal: {name}", True
    except Exception as exc:
        logger.exception("Tool %s gagal", name)
        return f"Terjadi kesalahan di panel: {type(exc).__name__}", True
    finally:
        conn.close()


def _result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _expected_token() -> str | None:
    conn = db.connect()
    try:
        return db.get_setting(conn, "mcp_token")
    finally:
        conn.close()


async def mcp_endpoint(request: Request):
    expected = await run_in_threadpool(_expected_token)
    if not expected or not security.same(request.headers.get("authorization"), f"Bearer {expected}"):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if request.method == "DELETE":
        return Response(status_code=200)
    if request.method != "POST":
        return Response(status_code=405)
    try:
        message = await request.json()
    except ValueError:
        return JSONResponse(_error(None, -32700, "JSON tidak valid"))
    if not isinstance(message, dict):
        return JSONResponse(_error(None, -32600, "Permintaan tidak valid"))
    msg_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    if msg_id is None:
        return Response(status_code=202)  # notifikasi
    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_VERSIONS else FALLBACK_VERSION
        result = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "jarvis-panel", "version": __version__},
        }
        return JSONResponse(_result(msg_id, result), headers={"Mcp-Session-Id": secrets.token_hex(16)})
    if method == "ping":
        return JSONResponse(_result(msg_id, {}))
    if method == "tools/list":
        return JSONResponse(_result(msg_id, {"tools": TOOLS}))
    if method == "tools/call":
        text, is_error = await run_in_threadpool(
            call_tool, str(params.get("name") or ""), params.get("arguments") or {}
        )
        return JSONResponse(_result(msg_id, {"content": [{"type": "text", "text": text}], "isError": is_error}))
    return JSONResponse(_error(msg_id, -32601, f"Method tidak dikenal: {method}"))


app = Starlette(routes=[Route("/mcp", mcp_endpoint, methods=["GET", "POST", "DELETE"])])
