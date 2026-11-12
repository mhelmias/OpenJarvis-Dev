#!/usr/bin/env python3
"""Server MCP (stdio) untuk jarvis-tools.

OpenJarvis menjalankannya lewat SSH. Setiap baris stdin berisi satu pesan
JSON-RPC, dan setiap balasan ditulis sebagai satu baris JSON di stdout.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

import files_tools
import store
import tasks_tools
from timeparse import WIB

SERVER_INFO = {"name": "jarvis-tools", "version": "0.2.0"}
TOOLS = tasks_tools.TOOLS + files_tools.TOOLS
SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
FALLBACK_VERSION = "2025-03-26"


class Server:
    def __init__(self) -> None:
        self._conn = None

    def _db(self):
        # Database baru dibuka saat tool pertama dipanggil, supaya tersambung tetap cepat.
        if self._conn is None:
            self._conn = store.connect()
        return self._conn

    def handle(self, message: dict):
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}
        if msg_id is None:
            return None  # notifikasi, tidak perlu dibalas
        if method == "initialize":
            requested = params.get("protocolVersion")
            version = requested if requested in SUPPORTED_VERSIONS else FALLBACK_VERSION
            return _result(msg_id, {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            })
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(msg_id, {"tools": TOOLS})
        if method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            try:
                if name in files_tools.NAMES:
                    text, is_error = files_tools.call_tool(name, args)
                else:
                    text, is_error = tasks_tools.call_tool(name, args, self._db(), datetime.now(WIB))
            except Exception as exc:  # misalnya database tidak bisa dibuka
                print(f"jarvis-tools: {type(exc).__name__}: {exc}", file=sys.stderr)
                text, is_error = f"Terjadi kesalahan di server: {type(exc).__name__}: {exc}", True
            return _result(msg_id, {
                "content": [{"type": "text", "text": text}],
                "isError": is_error,
            })
        return _error(msg_id, -32601, f"Method tidak dikenal: {method}")


def _result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def main() -> int:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    server = Server()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            reply = _error(None, -32700, "JSON tidak valid")
        else:
            if isinstance(message, dict):
                reply = server.handle(message)
            else:
                reply = _error(None, -32600, "Permintaan tidak valid")
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
