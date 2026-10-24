"""Tests for zingas_backup.py with a fake Backblaze B2 server. No real keys or data.

The lock tests need gpg; they are skipped where gpg is missing (Gerrit's laptop)
and run on Val's computer.
"""

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import threading
import unittest
import urllib.parse
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import zingas_backup as zb

HAS_GPG = shutil.which("gpg") is not None


class FakeB2(BaseHTTPRequestHandler):
    files = {}
    fail_uploads = 0
    page = 2
    key = ("kid", "ksecret")

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def base(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def do_GET(self):
        if self.path == "/b2api/v3/b2_authorize_account":
            want = "Basic " + base64.b64encode(":".join(self.key).encode()).decode()
            if self.headers.get("Authorization") != want:
                return self._send(401, {"message": "bad key"})
            return self._send(200, {"accountId": "acc", "authorizationToken": "tok", "apiInfo": {"storageApi": {
                "apiUrl": self.base(), "downloadUrl": self.base(),
                "allowed": {"buckets": [{"id": "bk1", "name": "vb"}]}}}})
        if self.path.startswith("/file/vb/"):
            if self.headers.get("Authorization") != "tok":
                return self._send(401, {"message": "no"})
            name = urllib.parse.unquote(self.path[len("/file/vb/"):])
            if name not in self.files:
                return self._send(404, {"message": "not found"})
            return self._send(200, self.files[name], "application/octet-stream")
        self._send(404, {"message": "?"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        if self.path == "/b2api/v3/b2_get_upload_url":
            assert self.headers.get("Authorization") == "tok"
            assert json.loads(body)["bucketId"] == "bk1"
            return self._send(200, {"uploadUrl": self.base() + "/upload", "authorizationToken": "up"})
        if self.path == "/upload":
            assert self.headers.get("Authorization") == "up"
            if FakeB2.fail_uploads:
                FakeB2.fail_uploads -= 1
                return self._send(503, {"message": "busy"})
            if hashlib.sha1(body).hexdigest() != self.headers.get("X-Bz-Content-Sha1"):
                return self._send(400, {"message": "sha1 mismatch"})
            name = urllib.parse.unquote(self.headers["X-Bz-File-Name"])
            FakeB2.files[name] = body
            return self._send(200, {"fileName": name, "contentSha1": hashlib.sha1(body).hexdigest()})
        if self.path == "/b2api/v3/b2_list_file_names":
            j = json.loads(body)
            names = sorted(k for k in self.files if k.startswith(j.get("prefix", "")))
            if j.get("startFileName"):
                names = [k for k in names if k >= j["startFileName"]]
            page, rest = names[:self.page], names[self.page:]
            return self._send(200, {"files": [{"fileName": k, "action": "upload"} for k in page],
                                    "nextFileName": rest[0] if rest else None})
        self._send(404, {"message": "?"})


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeB2)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.api = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        FakeB2.files, FakeB2.fail_uploads = {}, 0
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "hermes")
        self.vault = os.path.join(self.tmp, "vault")
        os.makedirs(os.path.join(self.vault, "customers"))
        os.makedirs(os.path.join(self.home, "cron"))
        os.makedirs(os.path.join(self.home, "skills", "__pycache__"))
        self.write(os.path.join(self.vault, "customers", "p1.md"), "likes white shutters")
        self.write(os.path.join(self.vault, "VOICE.md"), "short and warm")
        self.write(os.path.join(self.home, "SOUL.md"), "Val")
        self.write(os.path.join(self.home, ".env"), "TELEGRAM_BOT_TOKEN=secret")
        self.write(os.path.join(self.home, "auth.json"), "{}")
        self.write(os.path.join(self.home, "quo-bridge.env"), "VAL_DRAFT_TOKEN=x")
        self.write(os.path.join(self.home, "cron", ".jobs.lock"), "")
        self.write(os.path.join(self.home, "cron", "jobs.json"), '{"jobs": ["morning"]}')
        self.write(os.path.join(self.home, "skills", "__pycache__", "x.pyc"), "junk")
        db = sqlite3.connect(os.path.join(self.home, "state.db"))
        db.execute("create table s (v text)")
        db.execute("insert into s values ('hello')")
        db.commit()
        db.close()
        self.include = [self.vault, self.home]
        self.state = os.path.join(self.tmp, "backup-state.json")

    def write(self, path, text):
        with open(path, "w") as fh:
            fh.write(text)

    def b2(self, key_id="kid", key="ksecret", bucket=""):
        return zb.B2(key_id, key, bucket, api=self.api, timeout=5)


class PackTests(Base):
    def test_secrets_locks_and_caches_left_out(self):
        names = {os.path.basename(p) for p in zb.files_to_back_up(self.include)}
        self.assertTrue({"p1.md", "VOICE.md", "SOUL.md", "jobs.json", "state.db"} <= names)
        self.assertFalse(names & {".env", "auth.json", "quo-bridge.env", ".jobs.lock", "x.pyc"})

    def test_pack_and_unpack_keeps_database_and_paths(self):
        out = os.path.join(self.tmp, "b.tar.gz")
        info = zb.pack(self.include, out, self.tmp)
        self.assertEqual(info["files"], 5)
        names = zb.safe_extract(out, os.path.join(self.tmp, "out"))
        self.assertIn(zb.arcname(os.path.join(self.vault, "customers", "p1.md")), names)
        db = sqlite3.connect(os.path.join(self.tmp, "out", zb.arcname(os.path.join(self.home, "state.db"))))
        self.assertEqual(db.execute("select v from s").fetchall(), [("hello",)])
        db.close()
        c = zb.compare(os.path.join(self.tmp, "out"))
        self.assertEqual(c["missing_now"], [])
        self.assertIn(zb.arcname(os.path.join(self.vault, "VOICE.md")), c["same"])

    def test_unsafe_entries_refused(self):
        for bad in ("../evil.txt", "/etc/evil"):
            path = os.path.join(self.tmp, "bad.tar.gz")
            with tarfile.open(path, "w:gz") as tar:
                info = tarfile.TarInfo(bad)
                info.size = 1
                import io
                tar.addfile(info, io.BytesIO(b"x"))
            with self.assertRaises(zb.LockError):
                zb.safe_extract(path, os.path.join(self.tmp, "o"))
        path = os.path.join(self.tmp, "link.tar.gz")
        with tarfile.open(path, "w:gz") as tar:
            info = tarfile.TarInfo("link")
            info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            tar.addfile(info)
        with self.assertRaises(zb.LockError):
            zb.safe_extract(path, os.path.join(self.tmp, "o2"))


class ScheduleTests(unittest.TestCase):
    def at(self, day, h, m=0):
        return datetime(2026, 10, day, h, m, tzinfo=zb.TZ)

    def test_first_ever_runs_now(self):
        self.assertTrue(zb.due({}, self.at(23, 15)))

    def test_nightly_slot(self):
        st = {"last_ok": self.at(23, 2, 31).isoformat(), "last_try": self.at(23, 2, 31).isoformat()}
        self.assertFalse(zb.due(st, self.at(23, 20)))
        self.assertFalse(zb.due(st, self.at(24, 2, 29)))
        self.assertTrue(zb.due(st, self.at(24, 2, 30)))
        self.assertTrue(zb.due(st, self.at(24, 9)))     # computer was off at 2:30

    def test_retry_after_failure(self):
        ok = self.at(23, 2, 31).isoformat()
        st = {"last_ok": ok, "last_try": self.at(24, 2, 31).isoformat(), "last_error": "B2 503: busy"}
        self.assertFalse(zb.due(st, self.at(24, 2, 50)))
        self.assertTrue(zb.due(st, self.at(24, 3, 2)))

    def test_waiting_for_keys_checks_hourly(self):
        st = {"last_try": self.at(23, 15).isoformat(), "last_error": zb.WAITING}
        self.assertFalse(zb.due(st, self.at(23, 15, 45)))
        self.assertTrue(zb.due(st, self.at(23, 16, 1)))

    def test_brief_line(self):
        now = self.at(24, 8)
        self.assertEqual(zb.brief_line({}, now), "")
        self.assertEqual(zb.brief_line({"last_error": zb.WAITING}, now), "")
        self.assertEqual(zb.brief_line({"last_ok": self.at(24, 2, 31).isoformat()}, now), "")
        line = zb.brief_line({"last_ok": self.at(22, 2, 31).isoformat(), "last_error": "B2 401: bad key"}, now)
        self.assertTrue(line.startswith("BACKUP WARNING: last good backup Thursday 2:31 AM."))
        self.assertIn("bad key", line)
        self.assertIn("never", zb.brief_line({"last_error": "gpg failed"}, now))


class B2Tests(Base):
    def test_upload_list_download(self):
        b = self.b2()
        b.authorize()
        self.assertEqual((b.bucket_id, b.bucket_name), ("bk1", "vb"))
        src = os.path.join(self.tmp, "f.bin")
        with open(src, "wb") as fh:
            fh.write(os.urandom(5000))
        for n in ("nightly/val-2026-10-22-0230.tar.gz.gpg", "nightly/val-2026-10-23-0230.tar.gz.gpg",
                  "nightly/val-2026-10-24-0230.tar.gz.gpg"):
            b.upload(n, src)
        self.assertEqual(len(b.names()), 3)           # needs two pages from the fake
        dst = os.path.join(self.tmp, "back.bin")
        b.download(b.names()[-1], dst)
        self.assertEqual(zb.sha256(dst), zb.sha256(src))

    def test_upload_retries_when_busy(self):
        FakeB2.fail_uploads = 2
        b = self.b2()
        b.authorize()
        src = os.path.join(self.tmp, "f.bin")
        self.write(src, "data")
        b.upload("nightly/x", src)
        self.assertIn("nightly/x", FakeB2.files)

    def test_wrong_key_says_so(self):
        with self.assertRaises(zb.B2Error) as e:
            self.b2(key="nope").authorize()
        self.assertEqual(e.exception.status, 401)
        self.assertIn("bad key", str(e.exception))

    def test_wrong_bucket_name(self):
        with self.assertRaises(zb.B2Error):
            self.b2(bucket="other").authorize()


class BackupTests(Base):
    def test_waiting_for_keys(self):
        st = zb.backup_once({}, include=self.include, state_path=self.state)
        self.assertEqual(st["last_error"], zb.WAITING)
        self.assertEqual(FakeB2.files, {})

    @unittest.skipUnless(HAS_GPG, "gpg not installed here")
    def test_lock_unlock_and_wrong_password(self):
        src, locked, back = (os.path.join(self.tmp, x) for x in ("a", "a.gpg", "a.back"))
        self.write(src, "customer notes")
        zb.lock(src, locked, "pw-1")
        with open(locked, "rb") as fh:
            self.assertNotIn(b"customer notes", fh.read())
        with self.assertRaises(zb.LockError):
            zb.unlock(locked, back, "pw-2")
        zb.unlock(locked, back, "pw-1")
        self.assertEqual(zb.sha256(back), zb.sha256(src))

    @unittest.skipUnless(HAS_GPG, "gpg not installed here")
    def test_backup_then_restore_round_trip(self):
        keys = {"B2_KEY_ID": "kid", "B2_APP_KEY": "ksecret", "BACKUP_PASSPHRASE": "long-pass"}
        factory = lambda i, k, b="": zb.B2(i, k, b, api=self.api, timeout=5)
        st = zb.backup_once(keys, include=self.include, state_path=self.state, b2_factory=factory)
        self.assertEqual(st["last_error"], "")
        self.assertEqual(len(FakeB2.files), 1)
        stored = next(iter(FakeB2.files.values()))
        self.assertNotIn(b"white shutters", stored)
        out = os.path.join(self.tmp, "restored")
        res = zb.restore("kid", "ksecret", "long-pass", out, do_compare=True, b2_factory=factory)
        self.assertEqual(res["restored_files"], 5)
        self.assertEqual(res["changed"], [])
        self.assertEqual(res["missing_now"], [])
        with self.assertRaises(zb.LockError):
            zb.restore("kid", "ksecret", "wrong", os.path.join(self.tmp, "r2"), b2_factory=factory)

    def test_stored_total_adds_up_every_backup(self):
        # zingas-money bills Backblaze on the sum of every kept backup, not just the last one.
        # The lock is a plain copy here, so this runs without gpg.
        real = zb.lock, zb.unlock
        zb.lock = zb.unlock = lambda src, dst, pw: shutil.copyfile(src, dst)
        self.addCleanup(lambda: setattr(zb, "lock", real[0]) or setattr(zb, "unlock", real[1]))
        keys = {"B2_KEY_ID": "kid", "B2_APP_KEY": "ksecret", "BACKUP_PASSPHRASE": "long-pass"}
        factory = lambda i, k, b="": zb.B2(i, k, b, api=self.api, timeout=5)
        first = zb.backup_once(keys, now=datetime(2026, 10, 24, 2, 30, tzinfo=zb.TZ), include=self.include,
                               state_path=self.state, b2_factory=factory)
        second = zb.backup_once(keys, now=datetime(2026, 10, 25, 2, 30, tzinfo=zb.TZ), include=self.include,
                                state_path=self.state, b2_factory=factory)
        self.assertEqual(second["backups_ok"], 2)
        self.assertEqual(second["stored_bytes"], first["last_ok_bytes"] + second["last_ok_bytes"])
        self.assertEqual(sum(len(v) for v in FakeB2.files.values()), second["stored_bytes"])

    @unittest.skipUnless(HAS_GPG, "gpg not installed here")
    def test_apply_puts_files_back(self):
        keys = {"B2_KEY_ID": "kid", "B2_APP_KEY": "ksecret", "BACKUP_PASSPHRASE": "pw"}
        factory = lambda i, k, b="": zb.B2(i, k, b, api=self.api, timeout=5)
        zb.backup_once(keys, include=self.include, state_path=self.state, b2_factory=factory)
        newroot = os.path.join(self.tmp, "newbox")
        zb.restore("kid", "ksecret", "pw", os.path.join(self.tmp, "r"), apply=True, b2_factory=factory,
                   live_root=newroot)
        with open(os.path.join(newroot, zb.arcname(os.path.join(self.vault, "customers", "p1.md")))) as fh:
            self.assertEqual(fh.read(), "likes white shutters")

    @unittest.skipUnless(HAS_GPG, "gpg not installed here")
    def test_failed_upload_recorded_and_retried_later(self):
        keys = {"B2_KEY_ID": "kid", "B2_APP_KEY": "wrong", "BACKUP_PASSPHRASE": "pw"}
        factory = lambda i, k, b="": zb.B2(i, k, b, api=self.api, timeout=5)
        now = datetime(2026, 10, 24, 2, 30, tzinfo=zb.TZ)
        st = zb.backup_once(keys, now=now, include=self.include, state_path=self.state, b2_factory=factory)
        self.assertIn("401", st["last_error"])
        self.assertFalse(zb.due(st, now + timedelta(minutes=10)))
        self.assertTrue(zb.due(st, now + timedelta(minutes=31)))

    @unittest.skipUnless(HAS_GPG, "gpg not installed here")
    def test_self_check(self):
        res = zb.self_check(self.include)
        self.assertTrue(res["wrong_password_refused"])
        self.assertEqual(res["secrets_in_backup"], [])
        self.assertEqual(res["restored"], res["files"])


if __name__ == "__main__":
    unittest.main()
