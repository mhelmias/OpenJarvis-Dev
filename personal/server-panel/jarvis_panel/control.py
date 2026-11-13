"""Permintaan ke pembantu root (model dan kunci API) lewat folder spool.

Panel tidak punya hak mengubah OpenJarvis. Panel hanya menulis request.json; pembantu root
(jarvis-panel-helper, dijalankan systemd) membaca, memeriksa, menjalankan, lalu menulis
status.json dan result.json.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import time

from . import config

MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}$")
KEY_RE = re.compile(r"^[A-Za-z0-9._~+/=:-]{10,400}$")
ACTIONS = {"status", "models", "scan", "use", "key"}
STALE_RUNNING = 20 * 60


def _path(name: str) -> str:
    return os.path.join(config.SPOOL_DIR, name)


def _read(name: str):
    try:
        with open(_path(name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def status():
    return _read("status.json")


def result():
    return _read("result.json")


def running():
    data = _read("running.json")
    if data and time.time() - float(data.get("started_at") or 0) > STALE_RUNNING:
        return None
    return data


def busy() -> bool:
    return os.path.exists(_path("request.json")) or running() is not None


def submit(action: str, **fields) -> bool:
    """Tulis satu permintaan. False kalau masih ada permintaan lain yang diproses."""
    if action not in ACTIONS:
        raise ValueError(f"tindakan tidak dikenal: {action}")
    os.makedirs(config.SPOOL_DIR, mode=0o700, exist_ok=True)
    if busy():
        return False
    payload = {"id": secrets.token_hex(8), "action": action, "at": time.time(), **fields}
    fd, tmp = tempfile.mkstemp(dir=config.SPOOL_DIR, prefix=".req-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.chmod(tmp, 0o600)
        try:
            os.link(tmp, _path("request.json"))  # gagal kalau sudah ada permintaan lain
        except FileExistsError:
            return False
    finally:
        os.remove(tmp)
    return True
