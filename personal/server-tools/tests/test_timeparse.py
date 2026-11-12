import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jarvis_tools"))

from timeparse import WIB, WhenError, format_wib, parse_when  # noqa: E402

NOW = datetime(2026, 11, 11, 14, 0, tzinfo=WIB)  # Rabu, 11 November 2026 pukul 14.00


def wib(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=WIB)


CASES = [
    ("besok jam 9 pagi", wib(2026, 11, 12, 9)),
    ("jam 2 siang hari Jumat", wib(2026, 11, 13, 14)),
    ("30 menit lagi", wib(2026, 11, 11, 14, 30)),
    ("besok pagi jam 8", wib(2026, 11, 12, 8)),
    ("jam 8 malam", wib(2026, 11, 11, 20)),
    ("jam 9", wib(2026, 11, 12, 9)),
    ("jam 5", wib(2026, 11, 11, 17)),
    ("nanti malam", wib(2026, 11, 11, 19)),
    ("nanti sore jam 5", wib(2026, 11, 11, 17)),
    ("lusa jam 10", wib(2026, 11, 13, 10)),
    ("Senin depan jam 7 pagi", wib(2026, 11, 16, 7)),
    ("Senin minggu depan jam 9", wib(2026, 11, 16, 9)),
    ("Jumat depan jam 9", wib(2026, 11, 20, 9)),
    ("minggu depan jam 9", wib(2026, 11, 18, 9)),
    ("hari Minggu jam 7 pagi", wib(2026, 11, 15, 7)),
    ("Jum'at jam 2 siang", wib(2026, 11, 13, 14)),
    ("Jumat 2 siang", wib(2026, 11, 13, 14)),
    ("besok 9 pagi", wib(2026, 11, 12, 9)),
    ("tanggal 15 jam 10", wib(2026, 11, 15, 10)),
    ("tanggal 5 jam 10", wib(2026, 12, 5, 10)),
    ("20 Desember jam 9 pagi", wib(2026, 12, 20, 9)),
    ("15/11 jam 13.30", wib(2026, 11, 15, 13, 30)),
    ("2026-11-20T08:00", wib(2026, 11, 20, 8)),
    ("setengah jam lagi", wib(2026, 11, 11, 14, 30)),
    ("2 jam lagi", wib(2026, 11, 11, 16)),
    ("dalam 45 menit", wib(2026, 11, 11, 14, 45)),
    ("sejam lagi", wib(2026, 11, 11, 15)),
    ("1 jam 30 menit lagi", wib(2026, 11, 11, 15, 30)),
    ("tiga puluh menit lagi", wib(2026, 11, 11, 14, 30)),
    ("3 hari lagi", wib(2026, 11, 14, 14)),
    ("2 minggu lagi jam 9 pagi", wib(2026, 11, 25, 9)),
    ("jam setengah 8 malam", wib(2026, 11, 11, 19, 30)),
    ("jam setengah 7", wib(2026, 11, 12, 6, 30)),
    ("jam 12 malam", wib(2026, 11, 12, 0)),
    ("pukul 21.15", wib(2026, 11, 11, 21, 15)),
    ("besok jam 09:30", wib(2026, 11, 12, 9, 30)),
    ("besok jam 05.00", wib(2026, 11, 12, 5)),
    ("jam sembilan pagi besok", wib(2026, 11, 12, 9)),
    ("besok jam 9 lewat 15", wib(2026, 11, 12, 9, 15)),
    ("besok jam 9 kurang seperempat", wib(2026, 11, 12, 8, 45)),
    ("jam 7 kurang 15", wib(2026, 11, 12, 6, 45)),
    ("Besok, jam 7 pagi.", wib(2026, 11, 12, 7)),
]

ERRORS = [
    "",
    "besok",
    "kemarin jam 9",
    "hari ini jam 9 pagi",
    "jam 25",
    "Senin atau Selasa jam 9",
    "besok 30 menit lagi",
    "jam 9 lewat seratus",
    "2026-11-20",
    "tanggal 32 jam 9",
    "besok Jumat jam 9",
    "jam 13 pagi",
]


class ParseWhenTests(unittest.TestCase):
    def test_phrases(self):
        for phrase, expected in CASES:
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_when(phrase, NOW), expected)

    def test_errors(self):
        for phrase in ERRORS:
            with self.subTest(phrase=phrase):
                with self.assertRaises(WhenError):
                    parse_when(phrase, NOW)

    def test_format(self):
        self.assertEqual(format_wib(wib(2026, 11, 12, 9)), "Kamis, 12 November 2026 pukul 09.00 WIB")

    def test_default_now_is_future(self):
        self.assertGreater(parse_when("2 jam lagi"), datetime.now(WIB))


if __name__ == "__main__":
    unittest.main()
