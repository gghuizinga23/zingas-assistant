"""Tests for os_link.py: the shared do-not-contact list on the company website
(Zinga's OS) and the website's read-only drafts door. Nothing here reaches the
internet: urllib.request.urlopen is swapped for a fake that records each request."""

import contextlib
import io
import json
import unittest
import urllib.error
import urllib.parse
from unittest import mock

import app as wsgi
import os_link
from os_link import OsLink, SharedDncStore
from store import MemoryStore, SupabaseStore
from test_bridge import CUSTOMER, Rig

OS_URL = "https://zingas-os.example.com"
OS_TOKEN = "os-token-123"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeNet:
    """Stands in for urlopen. `replies` is a list of bytes or exceptions; with
    none left it answers "not on the list"."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append({"method": req.get_method(), "url": req.full_url, "timeout": timeout,
                              "headers": {k.lower(): v for k, v in req.header_items()},
                              "body": json.loads(req.data) if req.data else None})
        reply = self.replies.pop(0) if self.replies else b'{"doNotContact": false}'
        if isinstance(reply, Exception):
            raise reply
        return FakeResponse(reply)

    def posts(self):
        return [r for r in self.requests if r["method"] == "POST"]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def http_error(code):
    return urllib.error.HTTPError(OS_URL, code, "x", {}, io.BytesIO(b""))


def shared(store=None, clock=None):
    store = store or MemoryStore()
    return store, SharedDncStore(store, OsLink(OS_URL, OS_TOKEN, clock=clock or Clock()))


class DoNotContactChecks(unittest.TestCase):
    def test_website_flag_counts(self):
        _, s = shared()
        net = FakeNet(b'{"doNotContact": true, "sendWindow": {"startHour": 8, "endHour": 20}}')
        with mock.patch("urllib.request.urlopen", net):
            self.assertTrue(s.is_dnc(CUSTOMER))
        req = net.requests[0]
        self.assertEqual(req["method"], "GET")
        self.assertEqual(req["url"], OS_URL + "/api/assistant/contact?phone=3175550123")   # last 10 digits
        self.assertEqual(req["headers"]["authorization"], "Bearer " + OS_TOKEN)
        self.assertLessEqual(req["timeout"], 5)

    def test_clear_on_both_lists_means_ok_to_text(self):
        _, s = shared()
        with mock.patch("urllib.request.urlopen", FakeNet(b'{"doNotContact": false}')):
            self.assertFalse(s.is_dnc(CUSTOMER))

    def test_local_flag_counts_without_asking_the_website(self):
        store, s = shared()
        store.set_dnc(CUSTOMER, True, "x")
        net = FakeNet(b'{"doNotContact": false}')
        with mock.patch("urllib.request.urlopen", net):
            self.assertTrue(s.is_dnc(CUSTOMER))
        self.assertEqual(net.requests, [])

    def test_unsure_counts_as_do_not_contact(self):
        bad = [urllib.error.URLError("down"), TimeoutError(), http_error(500), http_error(401),
               b"<html>oops</html>", b'{"ok": true}', b'{"doNotContact": "no"}', b"[]"]
        for reply in bad:
            with self.subTest(reply=reply):
                _, s = shared()
                err = io.StringIO()
                with mock.patch("urllib.request.urlopen", FakeNet(reply)), contextlib.redirect_stderr(err):
                    self.assertTrue(s.is_dnc(CUSTOMER))
                self.assertIn("zingas-os", err.getvalue())
                self.assertEqual(err.getvalue().count("\n"), 1)                 # one line
                self.assertNotIn("5550123", err.getvalue())                      # never the phone
                self.assertNotIn(OS_TOKEN, err.getvalue())

    def test_after_a_failure_it_waits_before_asking_again(self):
        clock = Clock()
        _, s = shared(clock=clock)
        net = FakeNet(urllib.error.URLError("down"))
        with mock.patch("urllib.request.urlopen", net), contextlib.redirect_stderr(io.StringIO()):
            self.assertTrue(s.is_dnc(CUSTOMER))
            self.assertTrue(s.is_dnc(CUSTOMER))          # still unsure, didn't wait on the website again
            self.assertEqual(len(net.requests), 1)
            clock.t += os_link.COOL_OFF_SECONDS + 1
            self.assertFalse(s.is_dnc(CUSTOMER))         # asks again; the website says clear
            self.assertEqual(len(net.requests), 2)

    def test_other_store_calls_go_straight_through(self):
        store, s = shared()
        s.add_message({"id": "m1", "phone": CUSTOMER, "direction": "in", "body": "hi", "created_at": "t"})
        self.assertIn("m1", store.messages)


class StopAndStart(unittest.TestCase):
    def rig(self):
        r = Rig()
        r.bridge.store = SharedDncStore(r.store, OsLink(OS_URL, OS_TOKEN, clock=Clock()))
        return r

    def test_stop_puts_the_number_on_the_website_list(self):
        r = self.rig()
        net = FakeNet(b'{"ok": true}')
        with mock.patch("urllib.request.urlopen", net):
            self.assertEqual(r.customer_texts("STOP")[0], 200)
        self.assertTrue(r.store.is_dnc(CUSTOMER))                               # our own flag too
        self.assertEqual([(p["url"], p["body"]) for p in net.posts()],
                         [(OS_URL + "/api/assistant/contact", {"phone": "3175550123"})])
        self.assertEqual(net.posts()[0]["headers"]["authorization"], "Bearer " + OS_TOKEN)

    def test_stop_still_works_when_the_website_is_down(self):
        r = self.rig()
        err = io.StringIO()
        with mock.patch("urllib.request.urlopen", FakeNet(urllib.error.URLError("down"))), \
                contextlib.redirect_stderr(err):
            self.assertEqual(r.customer_texts("STOP")[0], 200)
        self.assertTrue(r.store.is_dnc(CUSTOMER))
        self.assertIn("zingas-os", err.getvalue())
        self.assertNotIn("5550123", err.getvalue())

    def test_start_clears_only_our_own_flag(self):
        r = self.rig()
        r.store.set_dnc(CUSTOMER, True, "x")
        net = FakeNet()
        with mock.patch("urllib.request.urlopen", net):
            r.customer_texts("START")
        self.assertFalse(r.store.is_dnc(CUSTOMER))
        self.assertEqual(net.posts(), [])

    def test_website_flag_stops_a_new_draft(self):
        r = self.rig()
        with mock.patch("urllib.request.urlopen", FakeNet(b'{"doNotContact": true}')):
            self.assertEqual(r.draft()[0], 409)
        self.assertEqual(r.tg.sent, [])


class DraftsDoor(unittest.TestCase):
    def rig(self):
        r = Rig()
        r.bridge.cfg.os_token = OS_TOKEN
        return r

    def test_no_or_wrong_code_is_refused(self):
        r = self.rig()
        self.assertEqual(r.call("GET", "/api/os/drafts")[0], 401)
        self.assertEqual(r.call("GET", "/api/os/drafts", headers={"Authorization": "Bearer guess"})[0], 401)
        self.assertEqual(r.val("GET", "/api/os/drafts")[0], 401)                 # Val's code isn't the website's
        self.assertEqual(r.call("POST", "/api/os/drafts", headers={"Authorization": "Bearer " + OS_TOKEN})[0], 405)

    def test_empty_code_never_matches(self):
        r = Rig()   # no ZINGAS_OS_TOKEN
        self.assertEqual(r.call("GET", "/api/os/drafts", headers={"Authorization": "Bearer "})[0], 401)

    def test_website_code_opens_nothing_else(self):
        r = self.rig()
        auth = {"Authorization": "Bearer " + OS_TOKEN}
        self.assertEqual(r.call("GET", "/api/val/updates", headers=auth)[0], 401)
        self.assertEqual(r.call("GET", "/api/tick", headers=auth)[0], 401)

    def test_shows_waiting_drafts_without_the_full_phone(self):
        r = self.rig()
        r.customer_texts("Can you come Thursday?")
        _, d = r.draft()
        r.store.update_draft(d["id"], {"final_body": "Thursday at 2 works!"})
        r.store.insert_draft({"id": "done1", "phone": CUSTOMER, "category": "reply", "body": "old",
                              "status": "sent", "created_at": "2026-10-01T00:00:00+00:00"})
        status, body = r.call("GET", "/api/os/drafts", headers={"Authorization": "Bearer " + OS_TOKEN})
        self.assertEqual(status, 200)
        self.assertEqual([x["id"] for x in body["drafts"]], [d["id"]])          # sent ones aren't listed
        row = body["drafts"][0]
        self.assertEqual(set(row), {"id", "customer_name", "phone_last4", "category", "body", "customer_said",
                                    "status", "reasons", "created_at", "send_after"})
        self.assertEqual(row["phone_last4"], "0123")
        self.assertEqual(row["body"], "Thursday at 2 works!")
        self.assertEqual(row["customer_said"], "Can you come Thursday?")
        self.assertEqual(row["status"], "pending")
        self.assertNotIn("5550123", json.dumps(body))


REQUIRED_ENV = {k: "x" for k in wsgi.REQUIRED}
REQUIRED_ENV["APPROVER_TELEGRAM_ID"] = "1"


class Settings(unittest.TestCase):
    def test_without_both_settings_nothing_changes(self):
        for extra in ({}, {"ZINGAS_OS_URL": OS_URL}, {"ZINGAS_OS_TOKEN": OS_TOKEN}):
            with self.subTest(extra=extra):
                b = wsgi.build_bridge(dict(REQUIRED_ENV, **extra))
                self.assertIs(type(b.store), SupabaseStore)

    def test_with_both_settings_the_shared_list_is_used(self):
        b = wsgi.build_bridge(dict(REQUIRED_ENV, ZINGAS_OS_URL=OS_URL + "/", ZINGAS_OS_TOKEN=OS_TOKEN))
        self.assertIsInstance(b.store, SharedDncStore)
        self.assertEqual(b.store.link.url, OS_URL + "/api/assistant/contact")
        self.assertEqual(b.cfg.os_token, OS_TOKEN)

    def test_drafts_door_is_shut_without_the_token(self):
        self.assertEqual(wsgi.build_bridge(REQUIRED_ENV).cfg.os_token, "")


if __name__ == "__main__":
    unittest.main()
