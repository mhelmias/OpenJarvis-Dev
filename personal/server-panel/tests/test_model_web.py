import json
import os
import re
import time

from starlette.testclient import TestClient

from jarvis_panel import config, control, db, security, tools_info, web_app

PASSWORD = "kata-sandi-uji-123"
KEY = "nvapi-RAHASIA-1234567890"


def client():
    conn = db.connect()
    db.set_setting(conn, "password_hash", security.hash_password(PASSWORD))
    conn.close()
    c = TestClient(web_app.app, follow_redirects=False)
    assert c.post("/masuk", data={"password": PASSWORD}).status_code == 303
    return c


def csrf_of(c, path="/model"):
    return re.search(r'name="csrf" value="([^"]+)"', c.get(path).text).group(1)


def spool(name):
    return os.path.join(config.SPOOL_DIR, name)


def write_spool(name, data):
    os.makedirs(config.SPOOL_DIR, exist_ok=True)
    with open(spool(name), "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def read_request():
    with open(spool("request.json"), encoding="utf-8") as fh:
        return json.load(fh)


STATUS = {
    "updated_at": time.time(), "provider": "nvidia", "model": "mistralai/mistral-large-4-1t-a52b",
    "engine": "nim", "service": "active",
    "providers": [
        {"id": "nvidia", "label": "NVIDIA build", "engine": "nim", "has_key": True,
         "suggested": ["deepseek-ai/deepseek-v4.1-flash"]},
        {"id": "openai", "label": "OpenAI", "engine": "cloud", "has_key": False, "suggested": []},
    ],
    "models": {"nvidia": {"updated_at": time.time(), "ids": ["a/model-satu", "b/model-dua"]}},
}


def test_model_page_requests_status_when_missing(state):
    c = client()
    page = c.get("/model")
    assert page.status_code == 200 and "Memuat status" in page.text
    assert read_request()["action"] == "status"
    assert 'http-equiv="refresh"' in page.text


def test_model_page_shows_active_model_and_models(state):
    write_spool("status.json", STATUS)
    c = client()
    page = c.get("/model").text
    assert "mistralai/mistral-large-4-1t-a52b" in page and "NVIDIA build" in page
    assert '<option value="a/model-satu">' in page
    assert "(belum ada kunci)" in page
    assert not os.path.exists(spool("request.json"))  # status masih segar
    assert "mistralai/mistral-large-4-1t-a52b" in c.get("/").text  # ringkasan di beranda


def test_use_model_validates_and_queues(state):
    write_spool("status.json", STATUS)
    c = client()
    token = csrf_of(c)
    bad = c.post("/model/ganti", data={"csrf": token, "provider": "nvidia", "model": "x; rm -rf /"})
    assert bad.status_code == 400 and "Nama model tidak valid" in bad.text
    nokey = c.post("/model/ganti", data={"csrf": token, "provider": "openai", "model": "gpt-x"})
    assert nokey.status_code == 400
    unknown = c.post("/model/ganti", data={"csrf": token, "provider": "evil", "model": "a/b"})
    assert unknown.status_code == 400
    ok = c.post("/model/ganti", data={"csrf": token, "provider": "nvidia", "model": "a/model-satu"})
    assert ok.status_code == 303 and "m=diproses" in ok.headers["location"]
    request = read_request()
    assert (request["action"], request["provider"], request["model"]) == ("use", "nvidia", "a/model-satu")
    busy = c.post("/model/muat", data={"csrf": token, "provider": "nvidia"})
    assert "m=sibuk" in busy.headers["location"]
    page = c.get("/model").text
    assert 'http-equiv="refresh"' in page and "disabled" in page


def test_save_key_never_shows_key(state):
    write_spool("status.json", STATUS)
    c = client()
    token = csrf_of(c)
    bad = c.post("/model/kunci", data={"csrf": token, "provider": "openai", "key": "ada spasi di sini"})
    assert bad.status_code == 400
    ok = c.post("/model/kunci", data={"csrf": token, "provider": "openai", "key": KEY})
    assert ok.status_code == 303
    assert read_request() | {"id": None, "at": None} == {
        "id": None, "at": None, "action": "key", "provider": "openai", "key": KEY}
    assert oct(os.stat(spool("request.json")).st_mode & 0o777) == "0o600"
    assert KEY not in c.get("/model").text


def test_result_details_are_escaped(state):
    write_spool("status.json", STATUS)
    write_spool("result.json", {
        "action": "scan", "provider": "nvidia", "ok": True, "message": "Uji selesai <b>",
        "details": [{"model": "a/ok", "status": "ok", "text": "bisa, 2 detik"},
                    {"model": "b/x", "status": "error", "text": "<script>alert(1)</script>"}],
        "finished_at": time.time()})
    page = client().get("/model").text
    assert "Uji selesai &lt;b&gt;" in page and "&lt;script&gt;" in page and "<script>" not in page


def test_control_submit_is_exclusive(state):
    assert control.submit("status") is True
    assert control.submit("status") is False
    os.remove(spool("request.json"))
    write_spool("running.json", {"action": "use", "started_at": time.time()})
    assert control.busy() and control.submit("status") is False
    write_spool("running.json", {"action": "use", "started_at": time.time() - 3600})
    assert not control.busy() and control.submit("status") is True


def test_tools_page(state, monkeypatch):
    items = [
        {"name": "add_reminder", "description": "Simpan tugas", "source": "mcp"},
        {"name": "ssh_run", "description": "Jalankan perintah", "source": "mcp"},
        {"name": "create_workbook", "description": "Create workbook <x>", "source": "mcp"},
        {"name": "calculator", "description": "Hitung", "source": "tool"},
        {"name": "shell_exec", "description": "Tidak aktif di kanal", "source": "tool"},
    ]
    monkeypatch.setattr(tools_info, "fetch", lambda: items)
    page = client().get("/tool").text
    assert "4 tool tersedia" in page
    for name in ["add_reminder", "ssh_run", "create_workbook", "calculator"]:
        assert name in page
    assert "shell_exec" not in page and "Create workbook &lt;x&gt;" in page


def test_tools_page_error(state, monkeypatch):
    def broken():
        raise OSError("mati")

    monkeypatch.setattr(tools_info, "fetch", broken)
    assert "belum bisa diambil" in client().get("/tool").text
