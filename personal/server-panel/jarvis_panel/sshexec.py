"""Menjalankan perintah lewat klien OpenSSH sistem, dengan kunci milik panel."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile

from . import config

HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")

# Lingkungan bersih untuk proses ssh: tidak ada token atau kunci yang ikut terbawa.
_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": config.STATE_DIR}


def _cap(text: str) -> str:
    if len(text) <= config.MAX_OUTPUT:
        return text
    return text[: config.MAX_OUTPUT] + f"\n... (dipotong, total {len(text)} karakter)"


def _base_args(server) -> list[str]:
    host, user = server["host"], server["username"]
    if not HOST_RE.match(host) or not USER_RE.match(user):
        raise ValueError("alamat atau nama pengguna server tidak sah")
    return [
        "ssh", "-T", "-F", "/dev/null",
        "-i", config.SSH_KEY,
        "-p", str(int(server["port"])),
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={config.KNOWN_HOSTS}",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=15",
        "-o", "LogLevel=ERROR",
        f"{user}@{host}",
    ]


def run(server, command: str, timeout: int) -> tuple[int, str]:
    """Jalankan perintah. Kembalikan (kode keluar, keluaran gabungan)."""
    try:
        args = _base_args(server) + ["--", command]
    except ValueError as exc:
        return 255, f"Tidak dijalankan: {exc}."
    try:
        proc = subprocess.run(
            args, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout,
            env=_ENV, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or b"") + (exc.stderr or b"")
        text = partial.decode("utf-8", "replace")
        return 124, _cap(text + f"\n(dihentikan setelah {timeout} detik)")
    except OSError as exc:
        return 255, f"ssh tidak bisa dijalankan: {exc}"
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    text = out if not err else (out + ("\n" if out and not out.endswith("\n") else "") + err)
    if proc.returncode == 255 and not out:
        text = "Gagal tersambung lewat SSH: " + (err.strip() or "tidak ada keterangan")
    return proc.returncode, _cap(text)


def ensure_keypair() -> None:
    os.makedirs(config.SSH_DIR, mode=0o700, exist_ok=True)
    if not os.path.exists(config.SSH_KEY):
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "jarvis-panel", "-f", config.SSH_KEY],
            check=True, env=_ENV,
        )
    if not os.path.exists(config.KNOWN_HOSTS):
        open(config.KNOWN_HOSTS, "a").close()
        os.chmod(config.KNOWN_HOSTS, 0o600)


def public_key() -> str:
    try:
        with open(config.SSH_KEY + ".pub", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _known_host_name(server) -> str:
    port = int(server["port"])
    return server["host"] if port == 22 else f"[{server['host']}]:{port}"


def trust_host_key(server) -> str:
    """Pindai kunci host server, simpan ke known_hosts panel, kembalikan sidik jarinya.

    Kunci lama untuk host yang sama dihapus dulu. Kalau server tidak bisa dihubungi,
    ValueError dilempar dengan pesan yang bisa ditampilkan.
    """
    if not HOST_RE.match(server["host"]):
        raise ValueError("alamat server tidak sah")
    scan = subprocess.run(
        ["ssh-keyscan", "-T", "5", "-p", str(int(server["port"])), "-t", "ed25519,ecdsa,rsa", server["host"]],
        capture_output=True, timeout=20, env=_ENV, check=False,
    )
    lines = [ln for ln in scan.stdout.decode("utf-8", "replace").splitlines() if ln and not ln.startswith("#")]
    if not lines:
        raise ValueError("server tidak menjawab pemindaian kunci host (cek alamat, port, dan SSH di server)")
    subprocess.run(
        ["ssh-keygen", "-R", _known_host_name(server), "-f", config.KNOWN_HOSTS],
        capture_output=True, env=_ENV, check=False,
    )
    with open(config.KNOWN_HOSTS, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    old_backup = config.KNOWN_HOSTS + ".old"
    if os.path.exists(old_backup):
        os.remove(old_backup)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=config.SSH_DIR) as tmp:
        tmp.write("\n".join(lines) + "\n")
    try:
        fp = subprocess.run(["ssh-keygen", "-l", "-f", tmp.name], capture_output=True, env=_ENV, check=False)
    finally:
        os.remove(tmp.name)
    return fp.stdout.decode("utf-8", "replace").strip()
