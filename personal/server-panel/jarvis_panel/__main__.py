"""Titik masuk: python -m jarvis_panel {web|mcp|setup|token|pubkey|add-server}."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import subprocess
import sys

from . import config, db, policy, security, sshexec


def _setup(change_password: bool) -> int:
    os.makedirs(config.STATE_DIR, exist_ok=True)
    sshexec.ensure_keypair()
    conn = db.connect()
    try:
        if not db.get_setting(conn, "mcp_token"):
            db.set_setting(conn, "mcp_token", security.new_token())
        if change_password or not db.get_setting(conn, "password_hash"):
            if not sys.stdin.isatty():
                print("Kata sandi panel perlu diketik di terminal. Jalankan: sudo jarvis-panel-setup")
                return 1
            while True:
                first = getpass.getpass(f"Kata sandi panel baru (minimal {security.MIN_PASSWORD} karakter): ")
                if len(first) < security.MIN_PASSWORD:
                    print("Terlalu pendek, coba lagi.")
                    continue
                if getpass.getpass("Ulangi kata sandi: ") != first:
                    print("Tidak sama, coba lagi.")
                    continue
                break
            db.set_setting(conn, "password_hash", security.hash_password(first))
            db.delete_all_sessions(conn)
            print("Kata sandi panel disimpan.")
    finally:
        conn.close()
    print("Panel siap.")
    return 0


def _add_server(args) -> int:
    conn = db.connect()
    try:
        if db.get_server_by_name(conn, args.name):
            print(f"Server {args.name} sudah ada.")
            return 0
        for value, pattern, label in ((args.name, sshexec.NAME_RE, "nama"), (args.host, sshexec.HOST_RE, "alamat"),
                                      (args.username, sshexec.USER_RE, "pengguna")):
            if not pattern.match(value):
                print(f"{label} tidak sah: {value}")
                return 1
        server_id = db.add_server(conn, name=args.name, host=args.host, port=args.port,
                                  username=args.username, mode=args.mode, note=args.note)
        server = db.get_server(conn, server_id)
        try:
            fingerprint = sshexec.trust_host_key(server)
            db.set_host_key(conn, server_id, fingerprint)
            print(f"Server {args.name} ditambahkan. Kunci host: {fingerprint}")
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            print(f"Server {args.name} ditambahkan, tetapi kunci host belum tersimpan: {exc}")
    finally:
        conn.close()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m jarvis_panel")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("web", help="jalankan panel web")
    sub.add_parser("mcp", help="jalankan server MCP untuk OpenJarvis")
    setup = sub.add_parser("setup", help="siapkan database, kunci SSH, token, dan kata sandi")
    setup.add_argument("--password", action="store_true", help="ganti kata sandi panel")
    sub.add_parser("token", help="cetak token MCP untuk konfigurasi OpenJarvis")
    sub.add_parser("pubkey", help="cetak kunci publik SSH panel")
    add = sub.add_parser("add-server", help="tambah server (dipakai skrip pasang)")
    add.add_argument("name")
    add.add_argument("host")
    add.add_argument("username")
    add.add_argument("--port", type=int, default=22)
    add.add_argument("--mode", default="setuju", choices=sorted(policy.MODES))
    add.add_argument("--note", default="")
    test = sub.add_parser("test", help="tes koneksi SSH ke server (menjalankan uname -a)")
    test.add_argument("name")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.cmd in ("web", "mcp"):
        import uvicorn

        if args.cmd == "web":
            from .web_app import app
            host = os.environ.get("JARVIS_PANEL_HOST", "127.0.0.1")
            port = int(os.environ.get("JARVIS_PANEL_PORT", "8020"))
        else:
            from .mcp_app import app
            host, port = "127.0.0.1", int(os.environ.get("JARVIS_PANEL_MCP_PORT", "8019"))
        uvicorn.run(app, host=host, port=port, proxy_headers=False, server_header=False,
                    date_header=False, access_log=False, log_level="warning")
        return 0
    if args.cmd == "setup":
        return _setup(args.password)
    if args.cmd == "token":
        conn = db.connect()
        try:
            token = db.get_setting(conn, "mcp_token")
        finally:
            conn.close()
        if not token:
            print("Belum ada token. Jalankan setup dulu.", file=sys.stderr)
            return 1
        print(token)
        return 0
    if args.cmd == "pubkey":
        key = sshexec.public_key()
        if not key:
            print("Belum ada kunci. Jalankan setup dulu.", file=sys.stderr)
            return 1
        print(key)
        return 0
    if args.cmd == "add-server":
        return _add_server(args)
    if args.cmd == "test":
        conn = db.connect()
        try:
            server = db.get_server_by_name(conn, args.name)
        finally:
            conn.close()
        if server is None:
            print(f"Server {args.name} tidak ada.")
            return 1
        code, output = sshexec.run(server, "uname -a", config.AUTO_TIMEOUT)
        print(("Tersambung: " if code == 0 else f"Gagal (kode {code}): ") + output.strip())
        return 0 if code == 0 else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
