import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from helpers import make_file
from file_organizer.core_engine import FileOrganizerEngine
from file_organizer.persistence import PersistenceManager
from file_organizer.web import MAX_BODY_BYTES, create_server


class WebCase(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp()
        self.data = tempfile.mkdtemp()
        pm = PersistenceManager(os.path.join(self.data, "h.json"), os.path.join(self.data, "a.csv"))
        self.server, self.app = create_server(pm, 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.work, ignore_errors=True)
        shutil.rmtree(self.data, ignore_errors=True)

    def call(self, method, path, body=None, token=True, host=None, raw=None, extra_headers=None):
        headers = {"Content-Type": "application/json"}
        if token is True:
            headers["X-Organizer-Token"] = self.app.token
        elif token:
            headers["X-Organizer-Token"] = token
        if host:
            headers["Host"] = host
        headers.update(extra_headers or {})
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as err:
            return err.code, err.read(), err.headers

    def jcall(self, *args, **kwargs):
        status, body, _ = self.call(*args, **kwargs)
        return status, json.loads(body)

    def w(self, *parts):
        return os.path.join(self.work, *parts)


class TestWebWorkflow(WebCase):
    def test_index_page_contains_token_and_security_headers(self):
        status, body, headers = self.call("GET", "/", token=False)
        self.assertEqual(status, 200)
        self.assertIn(self.app.token, body.decode())
        self.assertIn("Generate preview", body.decode())
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])

    def test_preview_organize_undo_roundtrip(self):
        make_file(self.work, "a.pdf", "x" * 10)
        make_file(self.work, "b.png")
        status, pv = self.jcall("POST", "/api/preview", {"path": self.work})
        self.assertEqual(status, 200)
        self.assertEqual(pv["total_files"], 2)
        self.assertEqual(pv["by_category"], {"Documents": 1, "Images": 1})
        self.assertTrue(os.path.exists(self.w("a.pdf")), "preview must not move anything")

        status, res = self.jcall("POST", "/api/organize", {"path": self.work, "atomic": True})
        self.assertEqual((status, res["successful"], res["failed"]), (200, 2, 0))
        self.assertTrue(os.path.exists(self.w("Documents", "a.pdf")))

        status, ops = self.jcall("GET", "/api/operations")
        op = ops["operations"][0]
        self.assertTrue(op["can_undo"])
        self.assertEqual(self.jcall("GET", "/api/stats")[1]["total_files_organized"], 2)

        status, undo = self.jcall("POST", "/api/undo", {"operation_id": op["operation_id"]})
        self.assertEqual((status, undo["restored"]), (200, 2))
        self.assertTrue(os.path.exists(self.w("a.pdf")))
        self.assertFalse(self.jcall("GET", "/api/operations")[1]["operations"][0]["can_undo"])
        status, again = self.jcall("POST", "/api/undo", {"operation_id": op["operation_id"]})
        self.assertEqual(status, 400)

    def test_include_subfolders_and_idempotence(self):
        make_file(self.work, "top.txt")
        make_file(self.work, "sub/deep/inner.pdf")
        self.assertEqual(self.jcall("POST", "/api/preview", {"path": self.work})[1]["total_files"], 1)
        pv = self.jcall("POST", "/api/preview", {"path": self.work, "recursive": True})[1]
        self.assertEqual(pv["total_files"], 2)
        self.jcall("POST", "/api/organize", {"path": self.work, "recursive": True})
        self.assertTrue(os.path.exists(self.w("Documents", "inner.pdf")))
        again = self.jcall("POST", "/api/preview", {"path": self.work, "recursive": True})[1]
        self.assertEqual(again["total_files"], 0, "already-organized files are left alone")
        ops = self.jcall("GET", "/api/operations")[1]["operations"]
        self.jcall("POST", "/api/undo", {"operation_id": ops[0]["operation_id"]})
        self.assertTrue(os.path.exists(self.w("sub", "deep", "inner.pdf")))

    def test_preview_reports_renames_and_truncates(self):
        make_file(self.work, "Documents/a.txt")
        make_file(self.work, "a.txt")
        pv = self.jcall("POST", "/api/preview", {"path": self.work})[1]
        self.assertTrue(pv["rows"][0]["renamed"])
        for i in range(210):
            make_file(self.work, f"f{i}.txt")
        pv = self.jcall("POST", "/api/preview", {"path": self.work})[1]
        self.assertTrue(pv["truncated"])
        self.assertEqual(len(pv["rows"]), 200)
        self.assertEqual(pv["total_files"], 211)

    def test_date_strategy_and_bad_strategy(self):
        make_file(self.work, "a.txt")
        pv = self.jcall("POST", "/api/preview", {"path": self.work, "strategy": "date"})[1]
        self.assertRegex(list(pv["by_category"])[0], r"^\d{4}-\d{2}$")
        self.assertEqual(self.jcall("POST", "/api/preview", {"path": self.work, "strategy": "bogus"})[0], 400)

    def test_duplicates_flow(self):
        make_file(self.work, "a.txt", "same")
        make_file(self.work, "b.txt", "same")
        status, scan = self.jcall("POST", "/api/duplicates/scan", {"path": self.work})
        self.assertEqual((scan["total_groups"], scan["total_extra_copies"]), (1, 1))
        status, res = self.jcall("POST", "/api/duplicates/quarantine", {"path": self.work})
        self.assertEqual(res["successful"], 1)
        self.assertEqual(len(os.listdir(self.w("Duplicates"))), 1)
        res = self.jcall("POST", "/api/duplicates/quarantine", {"path": self.work})[1]
        self.assertEqual(res["total"], 0)

    def test_report_download_and_crash_recovery_flag(self):
        make_file(self.work, "a.pdf")
        self.jcall("POST", "/api/organize", {"path": self.work})
        status, body, headers = self.call("GET", "/api/report")
        self.assertEqual(status, 200)
        self.assertIn("Executive Summary", body.decode())
        self.assertIn("attachment", headers["Content-Disposition"])
        with open(self.w(".organizer_journal.jsonl"), "w") as fh:
            fh.write(json.dumps({"src": self.w("x.txt"), "dst": self.w("Documents", "x.txt")}) + "\n")
        self.assertTrue(self.jcall("POST", "/api/preview", {"path": self.work})[1]["pending_recovery"])
        self.assertEqual(self.jcall("POST", "/api/recover", {"path": self.work})[0], 200)


class TestWebSecurity(WebCase):
    def test_token_required(self):
        self.assertEqual(self.call("POST", "/api/preview", {"path": self.work}, token=False)[0], 403)
        self.assertEqual(self.call("POST", "/api/preview", {"path": self.work}, token="wrong")[0], 403)
        self.assertEqual(self.call("GET", "/api/operations", token=False)[0], 403)
        self.assertEqual(self.call("GET", "/api/report", token=False)[0], 403)

    def test_foreign_host_header_rejected(self):
        self.assertEqual(self.call("GET", "/", token=False, host="evil.example.com")[0], 403)
        self.assertEqual(self.call("POST", "/api/preview", {"path": self.work}, host="evil.example.com")[0], 403)

    def test_bad_requests(self):
        self.assertEqual(self.jcall("POST", "/api/preview", {"path": ""})[0], 400)
        self.assertEqual(self.jcall("POST", "/api/preview", {"path": os.path.join(self.work, "nope")})[0], 400)
        status, body = self.jcall("POST", "/api/preview", {"path": "/"})
        self.assertEqual(status, 400)
        self.assertIn("protected", body["error"])
        self.assertEqual(self.call("POST", "/api/preview", raw=b"{not json")[0], 400)
        self.assertEqual(self.call("POST", "/api/preview", raw=b"[1,2]")[0], 400)
        self.assertEqual(self.call("POST", "/api/preview", raw=b"x" * (MAX_BODY_BYTES + 1))[0], 413)
        self.assertEqual(self.call("GET", "/nope", token=False)[0], 404)
        self.assertEqual(self.call("POST", "/api/nope", {})[0], 404)
        self.assertEqual(self.jcall("POST", "/api/undo", {"operation_id": "OP-NOPE"})[0], 404)

    def test_server_listens_on_loopback_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_page_never_inserts_server_data_as_html(self):
        _, body, _ = self.call("GET", "/", token=False)
        self.assertNotIn("innerHTML", body.decode())


if __name__ == "__main__":
    unittest.main()
