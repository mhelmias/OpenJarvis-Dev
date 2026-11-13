from starlette.testclient import TestClient

from jarvis_panel import db, mcp_app

TOKEN = "rahasia-uji"


def make_client():
    conn = db.connect()
    db.set_setting(conn, "mcp_token", TOKEN)
    conn.close()
    return TestClient(mcp_app.app)


def rpc(client, method, params=None, msg_id=1, token=TOKEN):
    body = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers={"Authorization": f"Bearer {token}"})


def call(client, name, **args):
    result = rpc(client, "tools/call", {"name": name, "arguments": args}).json()["result"]
    return result["content"][0]["text"], result["isError"]


def test_requires_token(state):
    client = make_client()
    assert rpc(client, "tools/list", token="salah").status_code == 401
    assert client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 401


def test_initialize_notification_and_tool_list(state):
    client = make_client()
    reply = rpc(client, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                       "clientInfo": {"name": "uji", "version": "0"}})
    assert reply.status_code == 200
    assert reply.headers.get("mcp-session-id")
    assert reply.json()["result"]["protocolVersion"] == "2025-03-26"
    notification = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                               headers={"Authorization": f"Bearer {TOKEN}"})
    assert notification.status_code == 202
    names = [tool["name"] for tool in rpc(client, "tools/list").json()["result"]["tools"]]
    assert names == ["ssh_servers", "ssh_run", "ssh_request"]


def test_read_only_command_runs_immediately(state, server, fake_ssh, sent):
    client = make_client()
    text, is_error = call(client, "ssh_run", server="ai", command="df -h", reason="cek disk")
    assert not is_error
    assert "#1" in text and "keluaran df -h" in text
    assert fake_ssh == [("ai", "df -h", 40)]
    assert sent == []


def test_changing_command_waits_for_approval(state, server, fake_ssh, sent):
    client = make_client()
    text, is_error = call(client, "ssh_run", server="ai", command="systemctl restart nginx",
                          reason="nginx macet")
    assert not is_error and "belum dijalankan" in text
    assert fake_ssh == []
    assert "http://panel.test:8020/permintaan/1" in sent[0]
    assert "systemctl restart nginx" in sent[0] and "nginx macet" in sent[0]
    text, _ = call(client, "ssh_request", request_id=1)
    assert "menunggu persetujuan" in text


def test_refused_unknown_and_listing(state, server, fake_ssh, sent):
    conn = db.connect()
    db.update_server(conn, server["id"], name="ai", host="127.0.0.1", port=22, username="jarvis-ops",
                     mode="baca", allow_patterns="", note="server utama")
    conn.close()
    client = make_client()
    text, is_error = call(client, "ssh_run", server="ai", command="rm -rf /tmp/x")
    assert is_error and "Ditolak" in text
    text, is_error = call(client, "ssh_run", server="tidak-ada", command="df -h")
    assert is_error and "tidak dikenal" in text
    text, _ = call(client, "ssh_servers")
    assert "ai: jarvis-ops@127.0.0.1, mode baca" in text and "server utama" in text
    assert fake_ssh == []
