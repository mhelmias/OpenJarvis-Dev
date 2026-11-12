import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent / "jarvis_tools"
sys.path.insert(0, str(CODE))

import send_due  # noqa: E402
import store  # noqa: E402
import tasks_tools  # noqa: E402
from timeparse import WIB  # noqa: E402

NOW = datetime(2026, 11, 11, 14, 0, tzinfo=WIB)  # Rabu


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = store.connect(os.path.join(self.tmp.name, "tasks.db"))

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def call(self, name, **args):
        return tasks_tools.call_tool(name, args, self.conn, NOW)


class ToolTests(DatabaseTestCase):
    def test_add_list_snooze_complete(self):
        text, is_error = self.call("add_reminder", title="Bayar listrik", when="besok jam 9 pagi")
        self.assertFalse(is_error, text)
        self.assertIn("tugas #1", text)
        self.assertIn("Kamis, 12 November 2026 pukul 09.00 WIB", text)

        text, _ = self.call("list_tasks")
        self.assertIn("Sekarang: Rabu, 11 November 2026 pukul 14.00 WIB", text)
        self.assertIn("#1 Bayar listrik", text)

        text, is_error = self.call("snooze_task", task_id=1, when="jam 8 malam")
        self.assertFalse(is_error, text)
        self.assertIn("Rabu, 11 November 2026 pukul 20.00 WIB", text)

        text, is_error = self.call("complete_task", task_id="#1")
        self.assertFalse(is_error, text)
        self.assertIn("ditandai selesai", text)

        text, _ = self.call("list_tasks", status="open")
        self.assertIn("Tidak ada tugas belum selesai", text)
        text, _ = self.call("list_tasks", status="done")
        self.assertIn("#1 Bayar listrik (selesai)", text)

    def test_errors_save_nothing(self):
        text, is_error = self.call("add_reminder", title="Rapat", when="besok")
        self.assertTrue(is_error)
        self.assertIn("Jam berapa", text)
        _, is_error = self.call("add_reminder", title="", when="besok jam 9")
        self.assertTrue(is_error)
        text, is_error = self.call("complete_task", task_id=99)
        self.assertTrue(is_error)
        self.assertIn("tidak ditemukan", text)
        _, is_error = self.call("tool_yang_tidak_ada")
        self.assertTrue(is_error)
        self.assertEqual(store.list_tasks(self.conn, "all"), [])


class SendDueTests(DatabaseTestCase):
    def test_sends_once_and_retries_after_failure(self):
        store.add_task(self.conn, "Minum obat", NOW - timedelta(minutes=1), "tes", NOW - timedelta(hours=1))
        store.add_task(self.conn, "Belum waktunya", NOW + timedelta(hours=1), "tes", NOW)

        def broken(text):
            raise RuntimeError("jaringan putus")

        self.assertEqual(send_due.run(self.conn, NOW, broken), (0, 1))
        sent = []
        self.assertEqual(send_due.run(self.conn, NOW, sent.append), (1, 0))
        self.assertIn("Minum obat", sent[0])
        self.assertNotIn("terlambat", sent[0])
        self.assertEqual(send_due.run(self.conn, NOW, sent.append), (0, 0))
        self.assertEqual(len(sent), 1)

    def test_late_notice(self):
        store.add_task(self.conn, "Telat", NOW - timedelta(minutes=90), "tes", NOW - timedelta(hours=3))
        sent = []
        send_due.run(self.conn, NOW, sent.append)
        self.assertIn("terlambat 1 jam 30 menit", sent[0])

    def test_completed_task_is_not_sent(self):
        task_id = store.add_task(self.conn, "Sudah", NOW - timedelta(minutes=1), "tes", NOW - timedelta(hours=1))
        store.complete_task(self.conn, task_id, NOW)
        sent = []
        self.assertEqual(send_due.run(self.conn, NOW, sent.append), (0, 0))


class McpServerTests(unittest.TestCase):
    def test_stdio_roundtrip(self):
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                        "clientInfo": {"name": "tes", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "add_reminder", "arguments": {"title": "Tes", "when": "2 jam lagi"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "list_tasks", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 5, "method": "metode/asing"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, JARVIS_TOOLS_DB=os.path.join(tmp, "tasks.db"))
            proc = subprocess.run(
                [sys.executable, "-s", "-E", str(CODE / "mcp_server.py")],
                input="".join(json.dumps(m) + "\n" for m in messages),
                capture_output=True, text=True, env=env, timeout=30,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        replies = [json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4, 5])
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-03-26")
        names = {tool["name"] for tool in replies[1]["result"]["tools"]}
        self.assertEqual(names, {"add_reminder", "list_tasks", "complete_task", "snooze_task",
                                 "list_files", "send_file"})
        self.assertFalse(replies[2]["result"]["isError"])
        self.assertIn("tugas #1", replies[2]["result"]["content"][0]["text"])
        self.assertIn("#1 Tes", replies[3]["result"]["content"][0]["text"])
        self.assertEqual(replies[4]["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
