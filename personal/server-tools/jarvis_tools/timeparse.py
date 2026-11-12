"""Mengubah frasa waktu bahasa Indonesia menjadi tanggal dan jam WIB.

Model AI cukup meneruskan frasa asli dari pengguna, misalnya "besok jam 9 pagi",
"30 menit lagi", atau "Jumat jam 2 siang". Semua hitungan tanggal dilakukan di
sini supaya hasilnya pasti dan bisa diuji.

Jam tanpa keterangan pagi/siang/sore/malam: jam 1-6 dianggap siang atau sore
(13.00-18.00), jam 7-11 dianggap pagi, dan jam 12 dianggap siang. Jam dengan nol
di depan (misalnya 05.00) atau jam 13-23 dipakai apa adanya.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timedelta, timezone

WIB = timezone(timedelta(hours=7), "WIB")

HARI = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
BULAN = (
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
)

_DAYS = {
    "senin": 0, "selasa": 1, "rabu": 2, "kamis": 3,
    "jumat": 4, "sabtu": 5, "minggu": 6, "ahad": 6,
}
_MONTHS = {
    "januari": 1, "jan": 1, "februari": 2, "pebruari": 2, "feb": 2,
    "maret": 3, "mar": 3, "april": 4, "apr": 4, "mei": 5,
    "juni": 6, "jun": 6, "juli": 7, "jul": 7,
    "agustus": 8, "agus": 8, "agt": 8, "agu": 8,
    "september": 9, "sept": 9, "sep": 9, "oktober": 10, "okt": 10,
    "november": 11, "nopember": 11, "nov": 11, "desember": 12, "des": 12,
}
_UNITS = {
    "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
    "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9,
}
# Jam bawaan bila hanya disebut "pagi", "sore", dan seterusnya: (jam, menit, tambah hari).
_PERIOD_DEFAULTS = {
    "subuh": (5, 0, 0),
    "pagi": (8, 0, 0),
    "siang": (12, 0, 0),
    "tengah hari": (12, 0, 0),
    "sore": (16, 0, 0),
    "petang": (18, 0, 0),
    "malam": (19, 0, 0),
    "tengah malam": (0, 0, 1),
}


def _alternatives(words) -> str:
    return "|".join(sorted(words, key=len, reverse=True))


_DAY_RE = _alternatives(_DAYS)
_MONTH_RE = _alternatives(_MONTHS)
_UNIT_RE = _alternatives(_UNITS)
_PERIOD_RE = "tengah malam|tengah hari|dini hari|subuh|pagi|siang|sore|petang|malam"
_AFTER = "(?:lagi|kemudian|dari sekarang)"
_EXAMPLES = "Contoh: 'besok jam 9 pagi', 'Jumat jam 2 siang', atau '30 menit lagi'."


class WhenError(ValueError):
    """Frasa waktu tidak bisa dipahami atau tidak valid. Pesannya aman untuk pengguna."""


def format_wib(dt: datetime) -> str:
    """Contoh hasil: 'Kamis, 12 November 2026 pukul 09.00 WIB'."""
    local = dt.astimezone(WIB)
    return (
        f"{HARI[local.weekday()]}, {local.day} {BULAN[local.month - 1]} "
        f"{local.year} pukul {local:%H.%M} WIB"
    )


def parse_when(text: str, now: datetime | None = None) -> datetime:
    """Ubah frasa waktu menjadi datetime WIB yang akan datang.

    Melempar WhenError berisi pesan untuk pengguna kalau frasanya kurang jelas,
    tidak dikenal, atau waktunya sudah lewat.
    """
    if now is None:
        now = datetime.now(WIB)
    now = now.astimezone(WIB).replace(second=0, microsecond=0)
    raw = (text or "").strip()
    if not raw:
        raise WhenError("Waktu pengingat belum disebut. Kapan pengingat ini perlu dikirim?")
    result = _parse_iso(raw)
    if result is None:
        result = _parse_phrase(_normalize(raw), now)
    if result <= now:
        raise WhenError(
            f"Waktu itu ({format_wib(result)}) sudah lewat. Sebutkan waktu yang akan datang."
        )
    if result > now + timedelta(days=5 * 366):
        raise WhenError("Waktunya lebih dari 5 tahun lagi. Periksa kembali tanggalnya.")
    return result


_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:[ t]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?)?(?:z|[+-]\d{2}:\d{2})?$",
    re.IGNORECASE,
)


def _parse_iso(raw: str) -> datetime | None:
    if not _ISO_RE.match(raw):
        return None
    if len(raw) == 10:
        raise WhenError(f"Tanggalnya sudah ada, tapi jam berapa? {_EXAMPLES}")
    text = raw.upper().replace(" ", "T")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        raise WhenError(f"Tanggal '{raw}' tidak valid.") from None
    if value.tzinfo is None:
        value = value.replace(tzinfo=WIB)
    return value.astimezone(WIB)


def _normalize(text: str) -> str:
    s = text.lower().replace("’", "'")
    s = re.sub(r"[,;!?\"()]", " ", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\bjum'? ?at\b", "jumat", s)
    s = re.sub(r"\b(?:pukul|pkl|pk)\b\.?", "jam", s)
    s = re.sub(r"\btgl\b\.?", "tanggal", s)
    s = re.sub(r"\bse(jam|menit|hari|minggu|pekan|bulan)\b", r"1 \1", s)
    s = re.sub(r"\bsepuluh\b", "10", s)
    s = re.sub(r"\bsebelas\b", "11", s)
    s = re.sub(
        rf"\b({_UNIT_RE}) puluh(?: ({_UNIT_RE}))?\b",
        lambda m: str(10 * _UNITS[m.group(1)] + (_UNITS[m.group(2)] if m.group(2) else 0)),
        s,
    )
    s = re.sub(rf"\b({_UNIT_RE}) belas\b", lambda m: str(10 + _UNITS[m.group(1)]), s)
    s = re.sub(rf"\b({_UNIT_RE})\b", lambda m: str(_UNITS[m.group(1)]), s)
    return re.sub(r"\s+", " ", s).strip()


class _Work:
    """Teks yang sedang diurai. Bagian yang sudah dikenali dihapus satu per satu."""

    def __init__(self, text: str) -> None:
        self.text = f" {text} "

    def take(self, pattern: str):
        match = re.search(pattern, self.text)
        if match:
            self.text = f"{self.text[:match.start()]} {self.text[match.end():]}"
        return match

    def ensure_nothing_left(self) -> None:
        left = re.sub(r"\s+", " ", self.text).strip(" .")
        if re.search(r"\d", left):
            raise WhenError(f"Bagian '{left}' tidak saya pahami. {_EXAMPLES}")
        leftover_time_words = (
            rf"\b(?:{_DAY_RE}|{_MONTH_RE}|{_PERIOD_RE}|besok|lusa|lewat|kurang|setengah|seperempat)\b"
        )
        if re.search(leftover_time_words, left):
            raise WhenError(
                f"Keterangan waktunya kurang jelas ('{left}'). Sebutkan satu waktu saja. {_EXAMPLES}"
            )


def _parse_phrase(s: str, now: datetime) -> datetime:
    work = _Work(s)
    today = now.date()

    # 1. Durasi pendek: "30 menit lagi", "dalam 2 jam", "1 jam 30 menit lagi".
    delta = None
    m = work.take(rf"\b(\d+) ?jam (\d+) ?menit {_AFTER}\b")
    if m:
        delta = timedelta(hours=int(m.group(1)), minutes=int(m.group(2)))
    else:
        m = work.take(rf"\b(?:dalam (?:waktu )?)?(\d+|setengah|seperempat) ?(menit|jam) {_AFTER}\b")
        if m is None:
            m = work.take(r"\bdalam (?:waktu )?(\d+|setengah|seperempat) ?(menit|jam)\b")
        if m:
            delta = _duration(m.group(1), m.group(2))
    if delta is not None:
        work.ensure_nothing_left()
        return now + delta

    # 2. Beberapa hari lagi: "3 hari lagi", "2 minggu lagi", "dalam 1 bulan".
    rel_days = None
    rel_months = None
    m = work.take(rf"\b(\d+) ?(hari|minggu|pekan|bulan) {_AFTER}\b")
    if m is None:
        m = work.take(r"\bdalam (?:waktu )?(\d+) ?(hari|minggu|pekan|bulan)\b")
    if m:
        amount = int(m.group(1))
        if m.group(2) == "bulan":
            rel_months = amount
        else:
            rel_days = amount * (7 if m.group(2) in ("minggu", "pekan") else 1)
    keep_clock = m is not None

    # 3. Tanggal tertulis: (hari, bulan, tahun). Bulan None berarti "tanggal 15" saja.
    explicit = None
    m = work.take(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
    if m:
        explicit = (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    if explicit is None:
        m = work.take(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
        if m:
            explicit = (int(m.group(1)), int(m.group(2)), _year(m.group(3)))
    if explicit is None:
        m = work.take(rf"\b(?:tanggal )?(\d{{1,2}}) ({_MONTH_RE})\b(?: (\d{{4}})\b)?")
        if m:
            explicit = (int(m.group(1)), _MONTHS[m.group(2)], _year(m.group(3)))
    if explicit is None:
        m = work.take(r"\btanggal (\d{1,2})\b")
        if m:
            explicit = (int(m.group(1)), None, None)

    # 4. Besok, lusa, hari ini.
    if work.take(r"\bkemarin\b"):
        raise WhenError("Waktu itu sudah lewat. Sebutkan waktu yang akan datang.")
    rel_word = None
    if work.take(r"\b(?:besok lusa|lusa)\b"):
        rel_word = 2
    elif work.take(r"\b(?:besok|esok)\b"):
        rel_word = 1
    elif work.take(r"\b(?:hari ini|nanti|ntar)\b"):
        rel_word = 0

    # 5. Nama hari dan "minggu depan".
    weekday = None
    modifier = None
    next_week = False
    m = work.take(rf"\bhari ({_DAY_RE})(?: (depan|ini))?\b")
    if m is None:
        next_week = work.take(r"\b(?:minggu|pekan) depan\b") is not None
        m = work.take(rf"\b({_DAY_RE})(?: (depan|ini))?\b")
    if m:
        weekday = _DAYS[m.group(1)]
        modifier = m.group(2) or ("depan" if next_week else None)
        next_week = False

    # 6. Jam.
    hour = minute = None
    literal = False
    shift = 0
    m = work.take(r"\b(?:jam )?setengah (\d{1,2})\b")
    if m:
        hour, minute, literal = _clock(m.group(1), None)
        shift = -30
    else:
        m = work.take(
            r"\bjam (\d{1,2})(?:[.:](\d{2}))?"
            r"(?: (lewat|lebih|kurang) (\d{1,2}|seperempat|setengah)(?: menit)?)?\b"
        )
        if m:
            hour, minute, literal = _clock(m.group(1), m.group(2))
            if m.group(3):
                amount = _minutes_word(m.group(4))
                shift = -amount if m.group(3) == "kurang" else amount
        else:
            m = work.take(r"\b(\d{1,2}):(\d{2})\b")
            if m is None:
                m = work.take(rf"\b(\d{{1,2}})(?:[.:](\d{{2}}))?(?= (?:{_PERIOD_RE})\b)")
            if m:
                hour, minute, literal = _clock(m.group(1), m.group(2))
    m = work.take(rf"\b({_PERIOD_RE})\b")
    period = m.group(1) if m else None

    work.ensure_nothing_left()

    # 7. Jam akhir.
    if hour is not None:
        hour, minute, extra = _apply_period(hour, minute, period, literal)
    elif period == "dini hari":
        raise WhenError("Jam berapa dini hari? Contoh: 'jam 3 dini hari'.")
    elif period is not None:
        hour, minute, extra = _PERIOD_DEFAULTS[period]
    elif keep_clock:
        hour, minute, extra = now.hour, now.minute, 0
    else:
        raise WhenError(f"Jam berapa pengingatnya? {_EXAMPLES}")

    def at(day: date) -> datetime:
        moment = datetime.combine(day + timedelta(days=extra), time(hour, minute), tzinfo=WIB)
        return moment + timedelta(minutes=shift)

    sources = [
        explicit is not None,
        rel_word is not None,
        weekday is not None,
        rel_days is not None or rel_months is not None,
        next_week,
    ]
    if sum(sources) > 1:
        raise WhenError(f"Keterangan harinya bertabrakan. Sebutkan satu hari saja. {_EXAMPLES}")

    # 8. Tanggal akhir.
    if explicit is not None:
        day_num, month, year = explicit
        if month is None:
            return _next_day_of_month(day_num, today, now, at)
        if year is not None:
            return at(_make_date(year, month, day_num))
        candidate = at(_make_date(today.year, month, day_num))
        if candidate <= now:
            candidate = at(_make_date(today.year + 1, month, day_num))
        return candidate
    if rel_word is not None:
        return at(today + timedelta(days=rel_word))
    if rel_days is not None:
        return at(today + timedelta(days=rel_days))
    if rel_months is not None:
        return at(_add_months(today, rel_months))
    if next_week:
        return at(today + timedelta(days=7))
    if weekday is not None:
        delta_days = (weekday - today.weekday()) % 7
        candidate = today + timedelta(days=delta_days)
        if modifier == "depan":
            if delta_days == 0:
                candidate += timedelta(days=7)
            if _week_start(candidate) == _week_start(today):
                candidate += timedelta(days=7)
        elif at(candidate) <= now:
            candidate += timedelta(days=7)
        return at(candidate)
    result = at(today)
    if result <= now:
        result = at(today + timedelta(days=1))
    return result


def _duration(amount: str, unit: str) -> timedelta:
    value = {"setengah": 0.5, "seperempat": 0.25}.get(amount)
    if value is None:
        value = int(amount)
    minutes = value * (60 if unit == "jam" else 1)
    if minutes <= 0:
        raise WhenError("Durasinya harus lebih dari nol.")
    return timedelta(minutes=minutes)


def _clock(hour_text: str, minute_text: str | None):
    hour = int(hour_text)
    minute = int(minute_text) if minute_text else 0
    if hour > 23 or minute > 59:
        shown = f"{hour_text}.{minute_text}" if minute_text else hour_text
        raise WhenError(f"Jam {shown} tidak valid.")
    literal = hour == 0 or hour >= 13 or (len(hour_text) == 2 and hour_text.startswith("0"))
    return hour, minute, literal


def _minutes_word(word: str) -> int:
    value = {"seperempat": 15, "setengah": 30}.get(word)
    if value is None:
        value = int(word)
    if value > 59:
        raise WhenError(f"{value} menit terlalu banyak. Gunakan jam, misalnya 'jam 10'.")
    return value


def _apply_period(hour: int, minute: int, period: str | None, literal: bool):
    """Terapkan pagi/siang/sore/malam. Kembalikan (jam, menit, tambah_hari)."""
    if period is None:
        if not literal and 1 <= hour <= 6:
            hour += 12
        return hour, minute, 0
    if period == "pagi" and 0 <= hour <= 11:
        return hour, minute, 0
    if period in ("siang", "tengah hari"):
        if hour in (11, 12) or 13 <= hour <= 17:
            return hour, minute, 0
        if 1 <= hour <= 5:
            return hour + 12, minute, 0
    if period in ("sore", "petang"):
        if 1 <= hour <= 7:
            return hour + 12, minute, 0
        if 13 <= hour <= 19:
            return hour, minute, 0
    if period == "malam":
        if 6 <= hour <= 11:
            return hour + 12, minute, 0
        if 18 <= hour <= 23:
            return hour, minute, 0
        if hour in (0, 12):
            return 0, minute, 1
        if 1 <= hour <= 4:
            return hour, minute, 1
    if period in ("subuh", "dini hari") and 0 <= hour <= 6:
        return hour, minute, 0
    if period == "tengah malam" and hour in (0, 12):
        return 0, minute, 1
    raise WhenError(f"Jam {hour} {period} kurang jelas. {_EXAMPLES}")


def _year(text: str | None) -> int | None:
    if not text:
        return None
    year = int(text)
    return year + 2000 if year < 100 else year


def _make_date(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError:
        raise WhenError(f"Tanggal {day}/{month}/{year} tidak ada.") from None


def _add_months(day: date, months: int) -> date:
    year, month = divmod(day.month - 1 + months, 12)
    year += day.year
    month += 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _next_day_of_month(day_num: int, today: date, now: datetime, at) -> datetime:
    for offset in range(3):
        year_add, month_index = divmod(today.month - 1 + offset, 12)
        try:
            candidate = at(date(today.year + year_add, month_index + 1, day_num))
        except ValueError:
            continue
        if candidate > now:
            return candidate
    raise WhenError(f"Tanggal {day_num} tidak ditemukan dalam beberapa bulan ke depan.")
