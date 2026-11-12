import os
import sys
import tempfile
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent / "jarvis_tools"
sys.path.insert(0, str(CODE))

import files_tools  # noqa: E402
import telegram_api  # noqa: E402


class FilesTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "files"
        (self.root / "laporan").mkdir(parents=True)
        (self.root / "anggaran.xlsx").write_bytes(b"PK\x03\x04isi-excel")
        (self.root / "laporan" / "q1.xlsx").write_bytes(b"PK\x03\x04q1")
        (self.root / ".tersembunyi").write_text("x")
        (self.root / "~$anggaran.xlsx").write_text("kunci")
        self.outside = base / "rahasia.txt"
        self.outside.write_text("rahasia")
        os.symlink(self.outside, self.root / "tautan.txt")

        self.env_file = base / "telegram.env"
        self.env_file.write_text("TELEGRAM_BOT_TOKEN=123:abc\nTELEGRAM_CHAT_ID=42\n")
        os.environ["JARVIS_TOOLS_TELEGRAM_ENV"] = str(self.env_file)

        self.sent = []
        self._old_root, self._old_sender = files_tools.FILES_ROOT, files_tools._send_document
        files_tools.FILES_ROOT = str(self.root)
        files_tools._send_document = lambda *args: self.sent.append(args)

    def tearDown(self):
        files_tools.FILES_ROOT, files_tools._send_document = self._old_root, self._old_sender
        os.environ.pop("JARVIS_TOOLS_TELEGRAM_ENV", None)
        self.tmp.cleanup()

    def call(self, name, **args):
        return files_tools.call_tool(name, args)


class ListFilesTests(FilesTestCase):
    def test_lists_visible_files_only(self):
        text, is_error = self.call("list_files")
        self.assertFalse(is_error, text)
        self.assertIn("anggaran.xlsx", text)
        self.assertIn(os.path.join("laporan", "q1.xlsx"), text)
        self.assertNotIn(".tersembunyi", text)
        self.assertNotIn("~$", text)

    def test_subfolder(self):
        text, is_error = self.call("list_files", folder="laporan")
        self.assertFalse(is_error, text)
        self.assertIn("q1.xlsx", text)
        self.assertNotIn("anggaran.xlsx", text)

    def test_empty_and_missing_folder(self):
        (self.root / "kosong").mkdir()
        text, is_error = self.call("list_files", folder="kosong")
        self.assertEqual((text, is_error), ("Folder kerja masih kosong.", False))
        text, is_error = self.call("list_files", folder="tidak-ada")
        self.assertTrue(is_error)


class SendFileTests(FilesTestCase):
    def test_sends_document(self):
        text, is_error = self.call("send_file", path="anggaran.xlsx", caption="Anggaran November")
        self.assertFalse(is_error, text)
        self.assertIn("sudah terkirim", text)
        token, chat_id, filename, data, caption = self.sent[0]
        self.assertEqual((token, chat_id, filename), ("123:abc", "42", "anggaran.xlsx"))
        self.assertEqual(data, b"PK\x03\x04isi-excel")
        self.assertEqual(caption, "Anggaran November")

    def test_refuses_paths_outside_root(self):
        for path in ["../rahasia.txt", str(self.outside), "tautan.txt", "/etc/passwd"]:
            text, is_error = self.call("send_file", path=path)
            self.assertTrue(is_error, path)
            self.assertIn("folder kerja", text)
        self.assertEqual(self.sent, [])

    def test_missing_empty_and_too_big(self):
        self.assertTrue(self.call("send_file", path="tidak-ada.xlsx")[1])
        self.assertTrue(self.call("send_file", path="")[1])
        self.assertTrue(self.call("send_file", path="laporan")[1])  # folder, bukan file
        old = files_tools.MAX_SEND_BYTES
        files_tools.MAX_SEND_BYTES = 3
        try:
            text, is_error = self.call("send_file", path="anggaran.xlsx")
        finally:
            files_tools.MAX_SEND_BYTES = old
        self.assertTrue(is_error)
        self.assertIn("50 MB", text)
        self.assertEqual(self.sent, [])

    def test_telegram_not_configured(self):
        os.environ["JARVIS_TOOLS_TELEGRAM_ENV"] = str(Path(self.tmp.name) / "tidak-ada.env")
        text, is_error = self.call("send_file", path="anggaran.xlsx")
        self.assertTrue(is_error)
        self.assertIn("Telegram belum diatur", text)

    def test_telegram_error_is_reported(self):
        def failing(*args):
            raise telegram_api.TelegramError("Bad Request: chat not found")

        files_tools._send_document = failing
        text, is_error = self.call("send_file", path="anggaran.xlsx")
        self.assertTrue(is_error)
        self.assertIn("chat not found", text)


class MultipartTests(unittest.TestCase):
    def test_body_layout(self):
        body, content_type = telegram_api.multipart(
            {"chat_id": "42", "caption": "Laporan"}, "document", 'lap"oran.xlsx', b"DATA"
        )
        boundary = content_type.split("boundary=", 1)[1]
        self.assertTrue(content_type.startswith("multipart/form-data; boundary=jarvis-"))
        self.assertIn(f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n42\r\n'.encode(), body)
        self.assertIn(b'name="caption"\r\n\r\nLaporan\r\n', body)
        self.assertIn(b'name="document"; filename="lap\'oran.xlsx"', body)
        self.assertIn(b"spreadsheetml", body)  # tipe file .xlsx dikenali
        self.assertIn(b"\r\n\r\nDATA\r\n", body)
        self.assertTrue(body.endswith(f"--{boundary}--\r\n".encode()))


if __name__ == "__main__":
    unittest.main()
