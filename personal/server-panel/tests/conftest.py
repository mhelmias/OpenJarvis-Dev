import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jarvis_panel import config, db, notify, sshexec  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "panel.db"))
    monkeypatch.setattr(config, "SSH_DIR", str(tmp_path / "ssh"))
    monkeypatch.setattr(config, "SSH_KEY", str(tmp_path / "ssh" / "id_ed25519"))
    monkeypatch.setattr(config, "KNOWN_HOSTS", str(tmp_path / "ssh" / "known_hosts"))
    monkeypatch.setattr(config, "PANEL_URL", "http://panel.test:8020")
    monkeypatch.setattr(config, "SPOOL_DIR", str(tmp_path / "spool"))
    monkeypatch.setattr(config, "OPENJARVIS_API", "http://openjarvis.test")
    return tmp_path


@pytest.fixture
def fake_ssh(monkeypatch):
    calls = []

    def run(server, command, timeout):
        calls.append((server["name"], command, timeout))
        return 0, f"keluaran {command}"

    monkeypatch.setattr(sshexec, "run", run)
    monkeypatch.setattr(sshexec, "trust_host_key", lambda server: "256 SHA256:abc host (ED25519)")
    monkeypatch.setattr(sshexec, "public_key", lambda: "ssh-ed25519 AAAATEST jarvis-panel")
    return calls


@pytest.fixture
def sent(monkeypatch):
    messages = []

    def send(text):
        messages.append(text)
        return True

    monkeypatch.setattr(notify, "send", send)
    return messages


@pytest.fixture
def server(state):
    conn = db.connect()
    server_id = db.add_server(conn, name="ai", host="127.0.0.1", port=22,
                              username="jarvis-ops", mode="setuju")
    row = db.get_server(conn, server_id)
    conn.close()
    return row
