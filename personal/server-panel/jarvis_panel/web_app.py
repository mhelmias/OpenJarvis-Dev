"""Panel web Jarvis: login, persetujuan perintah, daftar server, riwayat, pengaturan.

Halaman tanpa JavaScript. Keamanan: kata sandi scrypt, sesi di database dengan cookie
HttpOnly + SameSite=Strict, token CSRF di setiap formulir POST, batas percobaan login,
dan header CSP yang hanya mengizinkan gaya bawaan halaman.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone

import jinja2
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from . import actions, config, control, db, policy, security, sshexec, tools_info

WIB = timezone(timedelta(hours=7), "WIB")
COOKIE = "jp_session"
CSP = ("default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
       "frame-ancestors 'none'; base-uri 'none'")
MAX_FAILURES = 10

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
    autoescape=True,
)
_env.filters["wib"] = lambda ts: datetime.fromtimestamp(ts, WIB).strftime("%d-%m-%Y %H.%M") if ts else "-"
_env.globals["STATUS_TEXT"] = db.STATUS_TEXT
_env.globals["MODES"] = policy.MODES
_env.globals["ACTION_TEXT"] = {
    "status": "Muat status", "models": "Muat daftar model", "scan": "Uji model rekomendasi",
    "use": "Ganti model", "key": "Simpan kunci API",
}
templates = Jinja2Templates(env=_env)

NOTICES = {
    "masuk": ("ok", "Berhasil masuk."),
    "server-simpan": ("ok", "Perubahan server disimpan."),
    "server-hapus": ("ok", "Server dihapus."),
    "setujui": ("ok", "Disetujui. Perintah sedang dijalankan; hasilnya juga dikirim ke Telegram."),
    "tolak": ("ok", "Permintaan ditolak dan tidak dijalankan."),
    "sudah-diputus": ("err", "Permintaan ini sudah diputuskan atau sudah kedaluwarsa."),
    "sandi": ("ok", "Kata sandi diganti. Sesi di perangkat lain sudah dikeluarkan."),
    "diproses": ("ok", "Permintaan dikirim ke server. Halaman ini memuat ulang sendiri sampai selesai."),
    "sibuk": ("err", "Masih ada permintaan lain yang diproses. Tunggu sampai selesai."),
}


def _secure(response):
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


def _render(request, name: str, context: dict, status_code: int = 200):
    ctx = {"message": None, "message_kind": "", "logged_in": False, **context}
    notice = NOTICES.get(request.query_params.get("m", ""))
    if notice and not ctx["message"]:
        ctx["message_kind"], ctx["message"] = notice
    return _secure(templates.TemplateResponse(request, name, ctx, status_code=status_code))


def _redirect(url: str):
    return _secure(RedirectResponse(url, status_code=303))


def _set_session_cookie(response, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=config.SESSION_DAYS * 86400,
                        httponly=True, samesite="strict", path="/")


def page(handler):
    """Wajibkan login, periksa token CSRF untuk POST, lalu panggil handler."""

    async def endpoint(request):
        conn = db.connect()
        try:
            token = request.cookies.get(COOKIE)
            session = db.get_session(conn, token) if token else None
            if session is None:
                return _redirect("/masuk")
            form = None
            if request.method == "POST":
                form = await request.form()
                if not security.same(form.get("csrf"), session["csrf"]):
                    return _secure(PlainTextResponse(
                        "Token formulir tidak cocok. Muat ulang halaman lalu coba lagi.", status_code=403))
            base = {"logged_in": True, "csrf": session["csrf"]}
            return await handler(request, conn, session, form, base)
        finally:
            conn.close()

    return endpoint


# -- login ------------------------------------------------------------------------


async def login_page(request):
    conn = db.connect()
    try:
        ready = db.get_setting(conn, "password_hash") is not None
        if request.method == "GET":
            return _render(request, "masuk.html", {"ready": ready})
        form = await request.form()
        if not ready:
            return _render(request, "masuk.html", {"ready": False}, 400)
        if db.recent_login_failures(conn) >= MAX_FAILURES:
            return _render(request, "masuk.html", {
                "ready": True, "message_kind": "err",
                "message": "Terlalu banyak percobaan gagal. Tunggu 10 menit lalu coba lagi.",
            }, 429)
        stored = db.get_setting(conn, "password_hash")
        if not security.verify_password(str(form.get("password") or ""), stored):
            db.record_login_failure(conn)
            await asyncio.sleep(1)
            return _render(request, "masuk.html", {
                "ready": True, "message": "Kata sandi salah.", "message_kind": "err"}, 401)
        token, csrf = security.new_token(), security.new_token()
        db.create_session(conn, token, csrf)
        response = _redirect("/?m=masuk")
        _set_session_cookie(response, token)
        return response
    finally:
        conn.close()


@page
async def logout(request, conn, session, form, base):
    db.delete_session(conn, session["token"])
    response = _redirect("/masuk")
    response.delete_cookie(COOKIE, path="/")
    return response


# -- beranda dan permintaan ----------------------------------------------------------


@page
async def home(request, conn, session, form, base):
    db.expire_pending(conn)
    return _render(request, "beranda.html", {
        **base,
        "pending": db.list_requests(conn, status="pending", limit=50),
        "recent": db.list_requests(conn, limit=15),
        "servers": db.list_servers(conn),
        "model_status": control.status(),
    })


@page
async def request_detail(request, conn, session, form, base):
    rid = request.path_params["rid"]
    db.expire_pending(conn)
    row = db.get_request(conn, rid)
    if row is None:
        return _render(request, "pesan.html", {**base, "title": "Tidak ditemukan",
                                                "text": f"Permintaan #{rid} tidak ada."}, 404)
    return _render(request, "permintaan.html", {**base, "r": row})


@page
async def approve(request, conn, session, form, base):
    rid = request.path_params["rid"]
    if not db.decide(conn, rid, approve=True):
        return _redirect(f"/permintaan/{rid}?m=sudah-diputus")
    actions.run_approved_async(rid)
    return _redirect(f"/permintaan/{rid}?m=setujui")


@page
async def deny(request, conn, session, form, base):
    rid = request.path_params["rid"]
    if not db.decide(conn, rid, approve=False):
        return _redirect(f"/permintaan/{rid}?m=sudah-diputus")
    await run_in_threadpool(actions.notify_denied, db.get_request(conn, rid))
    return _redirect(f"/permintaan/{rid}?m=tolak")


@page
async def history(request, conn, session, form, base):
    db.expire_pending(conn)
    return _render(request, "riwayat.html", {**base, "rows": db.list_requests(conn, limit=200)})


# -- server ---------------------------------------------------------------------------


def _form_values(form) -> dict:
    return {
        "name": str(form.get("name") or "").strip().lower(),
        "host": str(form.get("host") or "").strip(),
        "port": str(form.get("port") or "22").strip(),
        "username": str(form.get("username") or "").strip(),
        "mode": str(form.get("mode") or "setuju"),
        "allow_patterns": str(form.get("allow_patterns") or "").replace("\r\n", "\n").strip(),
        "note": str(form.get("note") or "").strip(),
    }


def _validate(conn, values: dict, server_id: int | None = None) -> list[str]:
    errors = []
    if not sshexec.NAME_RE.match(values["name"]):
        errors.append("Nama hanya boleh huruf kecil, angka, dan tanda minus (maks 32), misalnya ai atau cloudpc.")
    else:
        existing = db.get_server_by_name(conn, values["name"])
        if existing and existing["id"] != server_id:
            errors.append("Nama server sudah dipakai.")
    if not sshexec.HOST_RE.match(values["host"]):
        errors.append("Alamat server tidak sah. Contoh: 100.64.0.10 atau nama-host.")
    try:
        port_ok = 1 <= int(values["port"]) <= 65535
    except ValueError:
        port_ok = False
    if not port_ok:
        errors.append("Port harus angka 1 sampai 65535.")
    if not sshexec.USER_RE.match(values["username"]):
        errors.append("Nama pengguna SSH tidak sah.")
    if values["mode"] not in policy.MODES:
        errors.append("Mode tidak dikenal.")
    bad = policy.invalid_patterns(values["allow_patterns"])
    if bad:
        errors.append("Pola izin bukan regex yang valid: " + ", ".join(bad[:3]))
    if len(values["allow_patterns"]) > 4000:
        errors.append("Pola izin terlalu panjang.")
    if len(values["note"]) > 300:
        errors.append("Catatan maksimal 300 karakter.")
    return errors


def _scan_key(server_id: int) -> tuple[str, str]:
    conn = db.connect()
    try:
        server = db.get_server(conn, server_id)
        try:
            fingerprint = sshexec.trust_host_key(server)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            return "err", f"Kunci host belum tersimpan: {exc}."
        db.set_host_key(conn, server_id, fingerprint)
        return "ok", "Kunci host server disimpan."
    finally:
        conn.close()


def _test_connection(server_id: int) -> tuple[str, str]:
    conn = db.connect()
    try:
        server = db.get_server(conn, server_id)
        rid = db.create_request(conn, server, "uname -a", "Tes koneksi dari panel", "tes", "running",
                                "Tes koneksi dari panel.")
        code, output = sshexec.run(server, "uname -a", config.AUTO_TIMEOUT)
        db.finish_request(conn, rid, code, output)
        if code == 0:
            return "ok", f"Tersambung: {output.strip()}"
        return "err", f"Belum tersambung (kode {code}): {output.strip()}"
    finally:
        conn.close()


def _server_context(conn, base: dict, server_id: int) -> dict:
    server = db.get_server(conn, server_id)
    return {**base, "server": server, "values": dict(server), "errors": [], "pubkey": sshexec.public_key()}


@page
async def servers_page(request, conn, session, form, base):
    return _render(request, "server_daftar.html", {
        **base, "servers": db.list_servers(conn), "pubkey": sshexec.public_key()})


@page
async def server_new(request, conn, session, form, base):
    if request.method == "GET":
        return _render(request, "server_form.html", {
            **base, "server": None, "errors": [], "pubkey": sshexec.public_key(),
            "values": {"port": "22", "mode": "setuju"}})
    values = _form_values(form)
    errors = _validate(conn, values)
    if errors:
        return _render(request, "server_form.html", {
            **base, "server": None, "values": values, "errors": errors,
            "pubkey": sshexec.public_key()}, 400)
    server_id = db.add_server(conn, name=values["name"], host=values["host"], port=int(values["port"]),
                              username=values["username"], mode=values["mode"],
                              allow_patterns=values["allow_patterns"], note=values["note"])
    kind, message = await run_in_threadpool(_scan_key, server_id)
    return _render(request, "server_form.html", {
        **_server_context(conn, base, server_id),
        "message_kind": kind, "message": "Server ditambahkan. " + message})


@page
async def server_edit(request, conn, session, form, base):
    server_id = request.path_params["sid"]
    server = db.get_server(conn, server_id)
    if server is None:
        return _render(request, "pesan.html", {**base, "title": "Tidak ditemukan",
                                                "text": "Server tidak ada."}, 404)
    if request.method == "GET":
        return _render(request, "server_form.html", _server_context(conn, base, server_id))
    values = _form_values(form)
    errors = _validate(conn, values, server_id)
    if errors:
        return _render(request, "server_form.html", {
            **base, "server": server, "values": values, "errors": errors,
            "pubkey": sshexec.public_key()}, 400)
    moved = (values["host"], int(values["port"])) != (server["host"], server["port"])
    db.update_server(conn, server_id, name=values["name"], host=values["host"],
                     port=int(values["port"]), username=values["username"], mode=values["mode"],
                     allow_patterns=values["allow_patterns"], note=values["note"])
    if moved:
        kind, message = await run_in_threadpool(_scan_key, server_id)
        return _render(request, "server_form.html", {
            **_server_context(conn, base, server_id),
            "message_kind": kind, "message": "Perubahan disimpan. " + message})
    return _redirect(f"/server/{server_id}?m=server-simpan")


@page
async def server_key(request, conn, session, form, base):
    server_id = request.path_params["sid"]
    if db.get_server(conn, server_id) is None:
        return _redirect("/server")
    kind, message = await run_in_threadpool(_scan_key, server_id)
    return _render(request, "server_form.html", {
        **_server_context(conn, base, server_id), "message_kind": kind, "message": message})


@page
async def server_test(request, conn, session, form, base):
    server_id = request.path_params["sid"]
    if db.get_server(conn, server_id) is None:
        return _redirect("/server")
    kind, message = await run_in_threadpool(_test_connection, server_id)
    return _render(request, "server_form.html", {
        **_server_context(conn, base, server_id), "message_kind": kind, "message": message})


@page
async def server_delete(request, conn, session, form, base):
    db.delete_server(conn, request.path_params["sid"])
    return _redirect("/server?m=server-hapus")


# -- model dan tool ----------------------------------------------------------------------


def _model_context(request, base: dict, chosen: str | None = None) -> dict:
    status = control.status()
    busy = control.busy()
    if not busy and (status is None or time.time() - float(status.get("updated_at") or 0) > 300):
        busy = control.submit("status") or control.busy()
    providers = (status or {}).get("providers") or []
    chosen = chosen or request.query_params.get("penyedia") or (status or {}).get("provider") or (
        providers[0]["id"] if providers else "")
    provider = next((p for p in providers if p["id"] == chosen), None)
    active = next((p for p in providers if p["id"] == (status or {}).get("provider")), None)
    cache = ((status or {}).get("models") or {}).get(chosen) or {}
    return {
        **base, "status": status, "result": control.result(), "running": control.running(),
        "busy": busy, "providers": providers, "provider": provider,
        "active_label": active["label"] if active else ((status or {}).get("provider") or "-"),
        "models": cache.get("ids") or [], "models_updated": cache.get("updated_at"),
    }


def _form_provider(form):
    status = control.status() or {}
    pid = str(form.get("provider") or "")
    return next((p for p in status.get("providers") or [] if p["id"] == pid), None)


def _model_error(request, base, form, message: str):
    ctx = _model_context(request, base, str(form.get("provider") or "") or None)
    ctx.update(message=message, message_kind="err")
    return _render(request, "model.html", ctx, 400)


def _after_submit(provider_id: str, submitted: bool):
    return _redirect(f"/model?penyedia={provider_id}&m={'diproses' if submitted else 'sibuk'}")


@page
async def model_page(request, conn, session, form, base):
    return _render(request, "model.html", _model_context(request, base))


@page
async def model_use(request, conn, session, form, base):
    provider = _form_provider(form)
    model = str(form.get("model") or "").strip()
    if provider is None:
        return _model_error(request, base, form, "Pilih penyedia dulu.")
    if not provider["has_key"]:
        return _model_error(request, base, form, "Penyedia ini belum punya kunci API. Simpan kuncinya dulu.")
    if not control.MODEL_RE.match(model):
        return _model_error(request, base, form, "Nama model tidak valid.")
    return _after_submit(provider["id"], control.submit("use", provider=provider["id"], model=model))


async def _provider_action(request, form, base, action: str):
    provider = _form_provider(form)
    if provider is None:
        return _model_error(request, base, form, "Pilih penyedia dulu.")
    if not provider["has_key"]:
        return _model_error(request, base, form, "Penyedia ini belum punya kunci API. Simpan kuncinya dulu.")
    return _after_submit(provider["id"], control.submit(action, provider=provider["id"]))


@page
async def model_load(request, conn, session, form, base):
    return await _provider_action(request, form, base, "models")


@page
async def model_scan(request, conn, session, form, base):
    return await _provider_action(request, form, base, "scan")


@page
async def model_key(request, conn, session, form, base):
    provider = _form_provider(form)
    key = str(form.get("key") or "").strip()
    if provider is None:
        return _model_error(request, base, form, "Pilih penyedia dulu.")
    if not control.KEY_RE.match(key):
        return _model_error(request, base, form, "Bentuk kunci tidak dikenali (ada spasi atau tanda aneh?).")
    return _after_submit(provider["id"], control.submit("key", provider=provider["id"], key=key))


@page
async def tools_page(request, conn, session, form, base):
    groups, error = await run_in_threadpool(tools_info.grouped)
    total = sum(len(group["tools"]) for group in groups)
    return _render(request, "tool.html", {**base, "groups": groups, "error": error, "total": total})


# -- pengaturan --------------------------------------------------------------------------


@page
async def settings_page(request, conn, session, form, base):
    context = {**base, "pubkey": sshexec.public_key(), "panel_url": config.PANEL_URL,
               "min_password": security.MIN_PASSWORD, "errors": []}
    if request.method == "GET":
        return _render(request, "pengaturan.html", context)
    old = str(form.get("old") or "")
    new = str(form.get("new") or "")
    again = str(form.get("again") or "")
    errors = []
    if not security.verify_password(old, db.get_setting(conn, "password_hash")):
        errors.append("Kata sandi lama salah.")
    if len(new) < security.MIN_PASSWORD:
        errors.append(f"Kata sandi baru minimal {security.MIN_PASSWORD} karakter.")
    if new != again:
        errors.append("Kata sandi baru dan ulangannya tidak sama.")
    if errors:
        return _render(request, "pengaturan.html", {**context, "errors": errors}, 400)
    db.set_setting(conn, "password_hash", security.hash_password(new))
    db.delete_all_sessions(conn)
    token, csrf = security.new_token(), security.new_token()
    db.create_session(conn, token, csrf)
    response = _redirect("/pengaturan?m=sandi")
    _set_session_cookie(response, token)
    return response


app = Starlette(routes=[
    Route("/masuk", login_page, methods=["GET", "POST"]),
    Route("/keluar", logout, methods=["POST"]),
    Route("/", home),
    Route("/permintaan/{rid:int}", request_detail),
    Route("/permintaan/{rid:int}/setujui", approve, methods=["POST"]),
    Route("/permintaan/{rid:int}/tolak", deny, methods=["POST"]),
    Route("/riwayat", history),
    Route("/server", servers_page),
    Route("/server/baru", server_new, methods=["GET", "POST"]),
    Route("/server/{sid:int}", server_edit, methods=["GET", "POST"]),
    Route("/server/{sid:int}/kunci", server_key, methods=["POST"]),
    Route("/server/{sid:int}/tes", server_test, methods=["POST"]),
    Route("/server/{sid:int}/hapus", server_delete, methods=["POST"]),
    Route("/model", model_page),
    Route("/model/ganti", model_use, methods=["POST"]),
    Route("/model/muat", model_load, methods=["POST"]),
    Route("/model/uji", model_scan, methods=["POST"]),
    Route("/model/kunci", model_key, methods=["POST"]),
    Route("/tool", tools_page),
    Route("/pengaturan", settings_page, methods=["GET", "POST"]),
])
