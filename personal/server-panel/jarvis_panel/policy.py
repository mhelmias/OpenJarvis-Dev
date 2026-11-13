"""Aturan perintah: mana yang langsung jalan, mana yang perlu persetujuan, mana yang ditolak.

Prinsipnya hati-hati: perintah hanya jalan otomatis kalau jelas hanya membaca keadaan
sistem. Ragu sedikit saja (tanda shell khusus, subperintah tak dikenal) berarti perlu
persetujuan pemilik, atau ditolak kalau server diatur hanya-baca.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

MODES = {
    "baca": "Hanya baca: perintah lain ditolak",
    "setuju": "Perintah selain baca menunggu persetujuan",
    "bebas": "Semua perintah langsung jalan (berbahaya)",
}

# Karakter yang bisa merangkai, mengalihkan, atau menyisipkan perintah lain.
_FORBIDDEN = set(";&$`<>(){}\\!#\n\r")

# Perintah yang hanya membaca. None = argumen apa pun boleh (kecuali yang ditolak di _DENY).
# Himpunan = argumen bukan-opsi pertama harus salah satu dari isinya.
_SAFE: dict[str, set[str] | None] = {
    "uptime": None, "hostname": None, "whoami": None, "id": None, "date": None,
    "uname": None, "lsb_release": None, "nproc": None, "free": None, "df": None,
    "du": None, "lsblk": None, "vmstat": None, "ps": None, "pgrep": None, "ss": None,
    "ls": None, "stat": None, "wc": None, "journalctl": None, "top": None,
    "systemctl": {"status", "is-active", "is-enabled", "is-failed", "list-units",
                  "list-timers", "list-unit-files", "show", "--failed"},
    "ip": {"a", "addr", "address", "r", "route", "link", "neigh"},
    "docker": {"ps", "images", "logs", "stats", "inspect", "version", "info"},
    "tailscale": {"status", "ip", "version"},
    "hostnamectl": {"status"},
    "timedatectl": {"status"},
    "apt": {"list"},
}

# Argumen yang membuat perintah "baca" di atas jadi mengubah sesuatu.
_DENY: dict[str, re.Pattern] = {
    "journalctl": re.compile(r"^--(vacuum|rotate|flush|sync|relinquish|setup-keys|update-catalog)"),
    "ip": re.compile(r"^(set|add|del|delete|change|replace|flush|append|prepend)$"),
    "hostname": re.compile(r"^(?!-)"),  # "hostname nama" mengganti nama host; hanya opsi yang boleh
    "date": re.compile(r"^(-s|--set)"),
    "systemctl": re.compile(r"^(restart|start|stop|reload|enable|disable|mask|kill|edit|set-property)$"),
}

# Perintah penyaring yang boleh menerima keluaran lewat "|".
_FILTERS = {"grep", "head", "tail", "sort", "uniq", "wc", "cut", "column"}


@dataclass(frozen=True)
class Decision:
    kind: str  # "auto", "approval", atau "refused"
    reason: str


def _segments(command: str) -> list[list[str]] | None:
    """Pecah perintah menjadi bagian-bagian di antara "|". None kalau tidak bisa dipastikan."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars="|")
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    segments, current = [], []
    for token in tokens:
        if token == "|":
            if not current:
                return None
            segments.append(current)
            current = []
        elif set(token) <= {"|"}:
            return None  # "||" dan sejenisnya
        else:
            current.append(token)
    if not current:
        return None
    segments.append(current)
    return segments


def _first_argument(args: list[str]) -> str | None:
    for arg in args:
        if not arg.startswith("-"):
            return arg
    return None


def _safe_main(tokens: list[str]) -> bool:
    name, args = tokens[0], tokens[1:]
    if name not in _SAFE:
        return False
    deny = _DENY.get(name)
    if deny and any(deny.search(arg) for arg in args):
        return False
    allowed = _SAFE[name]
    if allowed is not None:
        if name == "systemctl" and "--failed" in args and _first_argument(args) is None:
            return True
        first = _first_argument(args)
        if first is None and name in {"ip", "systemctl"}:
            return name == "systemctl"  # "systemctl" saja = list-units
        if first not in allowed:
            return False
    if name == "top" and not ({"-b", "-bn1"} & set(args) or any(a.startswith("-b") for a in args)):
        return False  # top tanpa -b menunggu terminal
    if name == "docker" and _first_argument(args) == "stats" and "--no-stream" not in args:
        return False
    if name == "docker" and _first_argument(args) == "logs" and any(a in {"-f", "--follow"} for a in args):
        return False
    if name == "journalctl" and any(a in {"-f", "--follow"} for a in args):
        return False
    return True


def _safe_filter(tokens: list[str]) -> bool:
    name, args = tokens[0], tokens[1:]
    if name not in _FILTERS:
        return False
    for arg in args:
        if arg.startswith(("/", "~", "..")) or "/" in arg and not arg.startswith("-"):
            return False  # penyaring tidak boleh membuka file sendiri
        if name == "grep" and (arg in {"--recursive", "-r", "-R", "-d", "-f"} or re.match(r"^-[a-zA-Z]*[rRdf]", arg)):
            return False
        if name in {"tail", "head"} and arg in {"-f", "-F", "--follow"}:
            return False
    return True


def is_read_only(command: str) -> bool:
    if not command or _FORBIDDEN & set(command):
        return False
    segments = _segments(command)
    if not segments:
        return False
    return _safe_main(segments[0]) and all(_safe_filter(seg) for seg in segments[1:])


def _matches_patterns(command: str, patterns: str) -> bool:
    if _FORBIDDEN & set(command):
        return False
    for line in (patterns or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            if re.fullmatch(line, command):
                return True
        except re.error:
            continue
    return False


def invalid_patterns(patterns: str) -> list[str]:
    bad = []
    for line in (patterns or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            re.compile(line)
        except re.error:
            bad.append(line)
    return bad


def classify(command: str, mode: str, allow_patterns: str = "") -> Decision:
    command = (command or "").strip()
    if not command:
        return Decision("refused", "Perintah kosong.")
    if len(command) > 2000:
        return Decision("refused", "Perintah terlalu panjang (lebih dari 2000 karakter).")
    if "\x00" in command:
        return Decision("refused", "Perintah memuat karakter tidak sah.")
    if mode == "bebas":
        return Decision("auto", "Server dalam mode bebas.")
    if is_read_only(command):
        return Decision("auto", "Perintah hanya membaca.")
    if _matches_patterns(command, allow_patterns):
        return Decision("auto", "Cocok dengan pola izin server.")
    if mode == "baca":
        return Decision(
            "refused",
            "Server ini hanya-baca, dan perintah ini bukan perintah baca yang diizinkan.",
        )
    return Decision("approval", "Perintah ini bisa mengubah sistem, jadi perlu persetujuan pemilik.")
