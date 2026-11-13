import re

from starlette.testclient import TestClient

from jarvis_panel import actions, db, security, web_app

PASSWORD = "kata-sandi-uji-123"


def make_client():
    conn = db.connect()
    if db.get_setting(conn, "password_hash") is None:
        db.set_setting(conn, "password_hash", security.hash_password(PASSWORD))
    conn.close()
    return TestClient(web_app.app, follow_redirects=False)


def login(client):
    reply = client.post("/masuk", data={"password": PASSWORD})
    assert reply.status_code == 303, reply.text
    return client


def csrf_of(client, path="/"):
    html = client.get(path).text
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def test_login_required_and_wrong_password(state):
    client = make_client()
    reply = client.get("/")
    assert reply.status_code == 303 and reply.headers["location"] == "/masuk"
    reply = client.post("/masuk", data={"password": "salah"})
    assert reply.status_code == 401 and "Kata sandi salah" in reply.text
    assert "default-src 'none'" in reply.headers["content-security-policy"]
    assert reply.headers["x-frame-options"] == "DENY"


def test_session_cookie_flags(state):
    reply = make_client().post("/masuk", data={"password": PASSWORD})
    cookie = reply.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_csrf_required(state, server):
    client = login(make_client())
    assert client.post(f"/server/{server['id']}/hapus", data={"csrf": "palsu"}).status_code == 403
    assert client.post(f"/server/{server['id']}/hapus", data={}).status_code == 403
    conn = db.connect()
    assert db.get_server(conn, server["id"]) is not None
    conn.close()


def test_approve_runs_command_and_reports(state, server, fake_ssh, sent, monkeypatch):
    conn = db.connect()
    rid = db.create_request(conn, server, "systemctl restart nginx", "macet", "approval", "pending")
    conn.close()
    monkeypatch.setattr(actions, "run_approved_async", actions._run_approved)  # tanpa thread
    client = login(make_client())
    token = csrf_of(client)
    assert "systemctl restart nginx" in client.get("/").text
    reply = client.post(f"/permintaan/{rid}/setujui", data={"csrf": token})
    assert reply.status_code == 303
    conn = db.connect()
    row = db.get_request(conn, rid)
    conn.close()
    assert row["status"] == "done" and row["output"] == "keluaran systemctl restart nginx"
    assert fake_ssh == [("ai", "systemctl restart nginx", 300)]
    assert sent[-1].startswith("✅ Perintah #1")
    again = client.post(f"/permintaan/{rid}/setujui", data={"csrf": token})
    assert "sudah-diputus" in again.headers["location"]
    assert len(fake_ssh) == 1


def test_deny(state, server, fake_ssh, sent):
    conn = db.connect()
    rid = db.create_request(conn, server, "reboot", "", "approval", "pending")
    conn.close()
    client = login(make_client())
    client.post(f"/permintaan/{rid}/tolak", data={"csrf": csrf_of(client)})
    conn = db.connect()
    assert db.get_request(conn, rid)["status"] == "denied"
    conn.close()
    assert fake_ssh == [] and sent[-1].startswith("⛔")


def test_add_server_validates_and_escapes(state, fake_ssh, sent):
    client = login(make_client())
    token = csrf_of(client, "/server/baru")
    bad = client.post("/server/baru", data={
        "csrf": token, "name": "Bad Name", "host": "-oProxyCommand=x", "port": "99999",
        "username": "root;", "mode": "setuju", "allow_patterns": "[rusak", "note": "<script>"})
    assert bad.status_code == 400
    for text in ["Nama hanya boleh", "Alamat server tidak sah", "Port harus",
                 "Nama pengguna SSH tidak sah", "Pola izin bukan regex"]:
        assert text in bad.text
    assert "<script>" not in bad.text and "&lt;script&gt;" in bad.text
    good = client.post("/server/baru", data={
        "csrf": token, "name": "cloudpc", "host": "100.64.0.10", "port": "22",
        "username": "jarvis-ops", "mode": "baca", "allow_patterns": "", "note": "Nextcloud"})
    assert good.status_code == 200 and "Server ditambahkan" in good.text and "SHA256:abc" in good.text
    conn = db.connect()
    assert db.get_server_by_name(conn, "cloudpc")["mode"] == "baca"
    conn.close()


def test_change_password_logs_out_other_sessions(state):
    first = login(make_client())
    second = login(make_client())
    token = csrf_of(first, "/pengaturan")
    short = first.post("/pengaturan", data={"csrf": token, "old": PASSWORD, "new": "pendek", "again": "pendek"})
    assert short.status_code == 400
    reply = first.post("/pengaturan", data={
        "csrf": token, "old": PASSWORD, "new": "sandi-baru-yang-panjang", "again": "sandi-baru-yang-panjang"})
    assert reply.status_code == 303
    assert first.get("/").status_code == 200
    assert second.get("/").status_code == 303
