"""Tests for store.py and clients.py. Nothing here reaches the internet:
urllib.request.urlopen is swapped for a fake that records each request."""

import base64
import io
import json
import unittest
import urllib.error
import urllib.parse
from unittest import mock

import clients
import store

SECRET = "whsec_" + base64.b64encode(b"k" * 24).decode()


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeNet:
    """Stands in for urlopen. `replies` is a list of bytes or exceptions."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, req, timeout=None):
        body = json.loads(req.data) if req.data else None
        self.requests.append({"method": req.get_method(), "url": req.full_url,
                              "headers": {k.lower(): v for k, v in req.header_items()}, "body": body})
        reply = self.replies.pop(0) if self.replies else b"[]"
        if isinstance(reply, Exception):
            raise reply
        return FakeResponse(reply)


def draft(id_="d1", status="pending", **kw):
    row = {"id": id_, "phone": "+13175550100", "time_zone": "America/Indiana/Indianapolis",
           "category": "followup", "body": "Hi!", "status": status,
           "created_at": "2026-10-21T15:00:00+00:00"}
    row.update(kw)
    return row


class MemoryStoreTests(unittest.TestCase):
    def test_claim_only_from_expected_status_and_only_once(self):
        s = store.MemoryStore()
        s.insert_draft(draft())
        first = s.claim_draft("d1", ["pending"], {"status": "approving"})
        second = s.claim_draft("d1", ["pending"], {"status": "approving"})
        self.assertEqual(first["status"], "approving")
        self.assertIsNone(second)
        self.assertIsNone(s.claim_draft("nope", ["pending"], {"status": "x"}))

    def test_claim_with_require_null(self):
        s = store.MemoryStore()
        s.insert_draft(draft())
        self.assertIsNotNone(s.claim_draft("d1", ["pending"], {"escalated_at": "t"}, require_null="escalated_at"))
        self.assertIsNone(s.claim_draft("d1", ["pending"], {"escalated_at": "t2"}, require_null="escalated_at"))

    def test_returned_rows_are_copies(self):
        s = store.MemoryStore()
        s.insert_draft(draft())
        got = s.get_draft("d1")
        got["status"] = "sent"
        self.assertEqual(s.get_draft("d1")["status"], "pending")

    def test_messages_pick_and_ack(self):
        s = store.MemoryStore()
        s.add_message({"id": "A2", "phone": "+1", "direction": "in", "body": "b", "created_at": "2026-10-21T15:01:00+00:00"})
        s.add_message({"id": "A1", "phone": "+1", "direction": "in", "body": "a", "created_at": "2026-10-21T15:00:00+00:00"})
        s.add_message({"id": "O1", "phone": "+1", "direction": "out", "body": "o", "created_at": "2026-10-21T15:02:00+00:00"})
        self.assertEqual([m["id"] for m in s.unpicked_messages()], ["A1", "A2"])
        s.ack_messages(["A1"], "now")
        self.assertEqual([m["id"] for m in s.unpicked_messages()], ["A2"])
        self.assertEqual(s.latest_inbound("+1")["id"], "A2")
        self.assertEqual([m["id"] for m in s.recent_messages("+1", 2)], ["A2", "O1"])

    def test_outcomes_only_finished_and_once(self):
        s = store.MemoryStore()
        s.insert_draft(draft("a", "sent"))
        s.insert_draft(draft("b", "pending"))
        self.assertEqual([d["id"] for d in s.unreported_outcomes()], ["a"])
        s.mark_reported(["a", "b"], "now")
        self.assertEqual(s.unreported_outcomes(), [])
        self.assertIsNone(s.get_draft("b").get("reported_at"))

    def test_dnc_and_stats(self):
        s = store.MemoryStore()
        self.assertFalse(s.is_dnc("+1"))
        s.set_dnc("+1", True, "now")
        self.assertTrue(s.is_dnc("+1"))
        self.assertEqual(s.get_stats("followup")["streak"], 0)
        s.save_stats("followup", 3, False)
        self.assertEqual(s.get_stats("followup")["streak"], 3)


class SupabaseStoreTests(unittest.TestCase):
    def setUp(self):
        self.s = store.SupabaseStore("https://abc.supabase.co/", "service-key")

    def test_new_style_secret_key_is_not_sent_as_bearer(self):
        net = FakeNet(b"[]")
        with mock.patch("urllib.request.urlopen", net):
            store.SupabaseStore("https://abc.supabase.co", "sb_secret_x").is_dnc("+1")
        self.assertEqual(net.requests[0]["headers"]["apikey"], "sb_secret_x")
        self.assertNotIn("authorization", net.requests[0]["headers"])

    def test_headers_and_insert_ignores_duplicates(self):
        net = FakeNet(b'[{"id":"AC1"}]', b"[]")
        with mock.patch("urllib.request.urlopen", net):
            self.assertTrue(self.s.add_message({"id": "AC1"}))
            self.assertFalse(self.s.add_message({"id": "AC1"}))
        r = net.requests[0]
        self.assertEqual(r["url"], "https://abc.supabase.co/rest/v1/messages?on_conflict=id")
        self.assertEqual(r["headers"]["apikey"], "service-key")
        self.assertEqual(r["headers"]["authorization"], "Bearer service-key")
        self.assertIn("resolution=ignore-duplicates", r["headers"]["prefer"])

    def test_claim_is_one_conditional_patch(self):
        net = FakeNet(b'[{"id":"d1","status":"approving"}]', b"[]")
        with mock.patch("urllib.request.urlopen", net):
            self.assertEqual(self.s.claim_draft("d1", ["pending", "failed"], {"status": "approving"})["status"], "approving")
            self.assertIsNone(self.s.claim_draft("d1", ["pending"], {"status": "approving"}, require_null="escalated_at"))
        first = net.requests[0]
        self.assertEqual(first["method"], "PATCH")
        self.assertEqual(urllib.parse.unquote(first["url"]),
                         'https://abc.supabase.co/rest/v1/drafts?id=eq.d1&status=in.("pending","failed")')
        self.assertEqual(first["body"], {"status": "approving"})
        self.assertIn("return=representation", first["headers"]["prefer"])
        self.assertTrue(net.requests[1]["url"].endswith("&escalated_at=is.null"))

    def test_phone_is_url_encoded(self):
        net = FakeNet(b'[{"do_not_contact":true}]')
        with mock.patch("urllib.request.urlopen", net):
            self.assertTrue(self.s.is_dnc("+13175550100"))
        self.assertIn("phone=eq.%2B13175550100", net.requests[0]["url"])

    def test_recent_messages_oldest_first(self):
        net = FakeNet(b'[{"id":"new"},{"id":"old"}]')
        with mock.patch("urllib.request.urlopen", net):
            self.assertEqual([m["id"] for m in self.s.recent_messages("+1")], ["old", "new"])

    def test_http_error_hides_details(self):
        err = urllib.error.HTTPError("https://abc.supabase.co/rest/v1/drafts?id=eq.x", 500, "boom", {}, None)
        with mock.patch("urllib.request.urlopen", FakeNet(err)):
            with self.assertRaises(store.StoreError) as cm:
                self.s.get_draft("x")
        self.assertIn("HTTP 500", str(cm.exception))
        self.assertNotIn("service-key", str(cm.exception))


class QuoClientTests(unittest.TestCase):
    def setUp(self):
        self.q = clients.QuoClient("quo-key", "PN123")

    def test_send_text_request(self):
        net = FakeNet(b'{"data":{"id":"AC9","status":"queued"}}')
        with mock.patch("urllib.request.urlopen", net):
            self.assertEqual(self.q.send_text("+13175550100", "Hi there"), "AC9")
        r = net.requests[0]
        self.assertEqual((r["method"], r["url"]), ("POST", "https://api.quo.com/v1/messages"))
        self.assertEqual(r["headers"]["authorization"], "quo-key")
        self.assertEqual(r["body"], {"content": "Hi there", "from": "PN123", "to": ["+13175550100"]})
        self.assertEqual(r["headers"]["user-agent"], "zingas-quo-bridge/1.0")   # not Python-urllib (Cloudflare 1010)

    def test_versioned_calls_send_the_version(self):
        net = FakeNet(b'{"data":[{"id":"PN1","phoneNumber":"+13175550000"}]}',
                      b'{"data":{"id":"7","key":"whsec_x"}}')
        with mock.patch("urllib.request.urlopen", net):
            self.assertEqual(self.q.list_numbers()[0]["id"], "PN1")
            self.assertEqual(self.q.create_webhook("https://h/api/quo", "PN1")["key"], "whsec_x")
        self.assertEqual(net.requests[0]["headers"]["quo-api-version"], "2026-03-30")
        self.assertEqual(net.requests[1]["body"]["events"], ["message.received"])
        self.assertEqual(net.requests[1]["body"]["resourceIds"], ["PN1"])

    def test_errors_explained_and_unknown_flagged(self):
        e400 = urllib.error.HTTPError("u", 400, "x", {}, None)
        with mock.patch("urllib.request.urlopen", FakeNet(e400)):
            with self.assertRaises(clients.QuoError) as cm:
                self.q.send_text("+1", "x")
        self.assertIn("registration", str(cm.exception))
        self.assertFalse(cm.exception.unknown)
        with mock.patch("urllib.request.urlopen", FakeNet(TimeoutError())):
            with self.assertRaises(clients.QuoError) as cm:
                self.q.send_text("+1", "x")
        self.assertTrue(cm.exception.unknown)


    def test_quo_own_words_are_kept(self):
        body = io.BytesIO(b'{"message":"Messaging not allowed: number not registered","code":"0201403","status":403,"title":"Forbidden"}')
        e403 = urllib.error.HTTPError("u", 403, "x", {}, body)
        with mock.patch("urllib.request.urlopen", FakeNet(e403)):
            with self.assertRaises(clients.QuoError) as cm:
                self.q.send_text("+1", "x")
        self.assertEqual(cm.exception.status, 403)
        self.assertIn("Quo said: Forbidden Messaging not allowed: number not registered", str(cm.exception))
        self.assertEqual(clients.quo_said(b"error code: 1010"), "error code: 1010")
        self.assertEqual(clients.quo_said(b"<html>blocked</html>"), "")
        self.assertEqual(clients.quo_said(b'{"error":{"message":"Missing authorization header"}}'),
                         "Missing authorization header")

class TelegramClientTests(unittest.TestCase):
    def setUp(self):
        self.t = clients.TelegramClient("123:SECRET")

    def test_send_with_buttons_and_force_reply(self):
        net = FakeNet(b'{"ok":true,"result":{"message_id":42}}', b'{"ok":true,"result":{"message_id":43}}')
        with mock.patch("urllib.request.urlopen", net):
            self.assertEqual(self.t.send(7, "hi", buttons=[[{"text": "OK", "callback_data": "a:1"}]]), 42)
            self.assertEqual(self.t.send(7, "type it", force_reply=True), 43)
        self.assertTrue(net.requests[0]["url"].endswith("/bot123:SECRET/sendMessage"))
        self.assertEqual(net.requests[0]["body"]["reply_markup"]["inline_keyboard"][0][0]["callback_data"], "a:1")
        self.assertEqual(net.requests[1]["body"]["reply_markup"], {"force_reply": True})

    def test_edit_and_answer(self):
        net = FakeNet(b'{"ok":true,"result":true}', b'{"ok":true,"result":true}')
        with mock.patch("urllib.request.urlopen", net):
            self.t.edit(7, 42, "done")
            self.t.answer("cb1", "Sent")
        self.assertEqual(net.requests[0]["body"]["reply_markup"], {"inline_keyboard": []})
        self.assertEqual(net.requests[1]["body"]["callback_query_id"], "cb1")

    def test_errors_never_show_the_token(self):
        err = urllib.error.HTTPError("https://api.telegram.org/bot123:SECRET/sendMessage", 401, "x", {}, None)
        with mock.patch("urllib.request.urlopen", FakeNet(err)):
            with self.assertRaises(clients.TelegramError) as cm:
                self.t.send(7, "hi")
        self.assertNotIn("SECRET", str(cm.exception))
        with mock.patch("urllib.request.urlopen", FakeNet(b'{"ok":false,"description":"chat not found"}')):
            with self.assertRaises(clients.TelegramError):
                self.t.send(7, "hi")


class SignatureTests(unittest.TestCase):
    def headers(self, body, ts=1000, msg_id="msg_1", secret=SECRET):
        return {"webhook-id": msg_id, "webhook-timestamp": str(ts),
                "webhook-signature": clients.sign_quo_body(body, secret, msg_id, ts)}

    def test_good_signature(self):
        self.assertTrue(clients.verify_quo_signature(self.headers(b"{}"), b"{}", SECRET, now=1100))

    def test_rejections(self):
        h = self.headers(b"{}")
        self.assertFalse(clients.verify_quo_signature(h, b"{} ", SECRET, now=1100))        # body changed
        self.assertFalse(clients.verify_quo_signature(h, b"{}", SECRET, now=1000 + 301))   # too old
        other = "whsec_" + base64.b64encode(b"z" * 24).decode()
        self.assertFalse(clients.verify_quo_signature(h, b"{}", other, now=1100))          # wrong key
        self.assertFalse(clients.verify_quo_signature({}, b"{}", SECRET, now=1100))        # no headers
        self.assertFalse(clients.verify_quo_signature(h, b"{}", "", now=1100))             # no secret

    def test_one_of_several_signatures(self):
        h = self.headers(b"{}")
        h["webhook-signature"] = "v1,AAAA " + h["webhook-signature"]
        self.assertTrue(clients.verify_quo_signature(h, b"{}", SECRET, now=1100))


class ParseTimeTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(store.parse_time("2026-10-21T15:00:00Z").hour, 15)
        self.assertEqual(store.parse_time("2026-10-21 15:00:00.12345+00:00").microsecond, 123450)
        self.assertIsNone(store.parse_time(None))


if __name__ == "__main__":
    unittest.main()
