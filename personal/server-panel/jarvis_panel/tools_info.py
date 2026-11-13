"""Daftar tool yang dipakai OpenJarvis di Telegram, diambil dari API OpenJarvis."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import config

# Tool bawaan OpenJarvis yang aktif untuk kanal Telegram (bawaan `jarvis serve`).
CHANNEL_BUILTINS = ["think", "calculator", "web_search"]
JARVIS_TOOLS = ["add_reminder", "list_tasks", "complete_task", "snooze_task", "list_files", "send_file"]
SSH_TOOLS = ["ssh_servers", "ssh_run", "ssh_request"]


def fetch() -> list[dict]:
    with urllib.request.urlopen(f"{config.OPENJARVIS_API}/v1/tools", timeout=8) as resp:
        data = json.load(resp)
    items = data.get("tools") if isinstance(data, dict) else data
    return [item for item in (items or []) if isinstance(item, dict) and item.get("name")]


def grouped() -> tuple[list[dict], str | None]:
    """Kembalikan (kelompok tool, pesan galat)."""
    try:
        items = fetch()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return [], f"Daftar tool belum bisa diambil dari OpenJarvis ({type(exc).__name__}). Pastikan OpenJarvis menyala."
    by_name = {item["name"]: item for item in items}
    known = set(JARVIS_TOOLS) | set(SSH_TOOLS)
    groups = [
        {"title": "Pengingat dan file", "source": "jarvis-tools (server MCP sendiri)",
         "tools": [by_name[n] for n in JARVIS_TOOLS if n in by_name]},
        {"title": "Kelola server lewat SSH", "source": "Jarvis Panel (server MCP sendiri)",
         "tools": [by_name[n] for n in SSH_TOOLS if n in by_name]},
        {"title": "Excel", "source": "excel-mcp-server (pihak ketiga)",
         "tools": [i for i in items if i.get("source") == "mcp" and i["name"] not in known]},
        {"title": "Bawaan OpenJarvis", "source": "OpenJarvis",
         "tools": [by_name[n] for n in CHANNEL_BUILTINS if n in by_name]},
    ]
    return [group for group in groups if group["tools"]], None
