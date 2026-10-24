"""F0 additions to store.py and clients.py, against a fake network."""

import json
import unittest
import urllib.error
import urllib.parse
from unittest import mock

import clients
import store
from test_store_clients import FakeNet


class SupabaseFollowupTests(unittest.TestCase):
    def setUp(self):
        self.s = store.SupabaseStore("https://abc.supabase.co/", "service-key")

    def url(self, net, n=0):
        return urllib.parse.unquote(net.requests[n]["url"]).replace("https://abc.supabase.co/rest/v1/", "")

    def test_insert_if_new(self):
        net = FakeNet(b'[{"id":"f1"}]', b"[]")
        with mock.patch("urllib.request.urlopen", net):
            self.assertTrue(self.s.insert_draft_if_new({"id": "f1"}))
            self.assertFalse(self.s.insert_draft_if_new({"id": "f1"}))
        self.assertEqual(self.url(net), "drafts?on_conflict=id")
        self.assertIn("ignore-duplicates", net.requests[0]["headers"]["prefer"])

    def test_outcomes_split_by_category(self):
        net = FakeNet(b"[]", b"[]")
        with mock.patch("urllib.request.urlopen", net):
            self.s.unreported_outcomes(20, exclude_category="followup")
            self.s.unreported_outcomes(50, category="followup")
        self.assertIn("&category=neq.followup&", self.url(net, 0))
        self.assertIn("&category=eq.followup&", self.url(net, 1))
        self.assertIn('"paused"', self.url(net, 0))

    def test_followups_for_phone_and_email(self):
        net = FakeNet(b'[{"id":"a"}]', b'[{"id":"a"},{"id":"b"}]')
        with mock.patch("urllib.request.urlopen", net):
            rows = self.s.followups_for(["held"], phone="+13175550100", email="Pat@Example.com")
        self.assertEqual([r["id"] for r in rows], ["a", "b"])
        self.assertIn("phone=eq.+13175550100", self.url(net, 0))
        self.assertIn("email_to=eq.pat@example.com", self.url(net, 1))

    def test_bulk_messages_and_dnc(self):
        net = FakeNet(b"[]", b'[{"phone":"+13175550100"}]')
        with mock.patch("urllib.request.urlopen", net):
            self.s.messages_for_phones(["+13175550100", "+13175550101"])
            self.assertEqual(self.s.dnc_phones(["+13175550100"]), ["+13175550100"])
        self.assertIn('phone=in.("+13175550100","+13175550101")', self.url(net, 0))
        self.assertIn("do_not_contact=is.true", self.url(net, 1))

    def test_batches(self):
        net = FakeNet(b"[]", b'[{"id":"2026-10-26","tg_message_id":7}]')
        with mock.patch("urllib.request.urlopen", net):
            self.s.save_batch("2026-10-26", {"tg_message_id": 7})
            self.assertEqual(self.s.get_batch("2026-10-26")["tg_message_id"], 7)
        self.assertEqual(net.requests[0]["body"], [{"tg_message_id": 7, "id": "2026-10-26"}])
        self.assertIn("merge-duplicates", net.requests[0]["headers"]["prefer"])


class ComposioGmailTests(unittest.TestCase):
    def setUp(self):
        self.g = clients.ComposioGmail("main-key", "ca_123")

    def test_reply_in_thread(self):
        net = FakeNet(json.dumps({"successful": True, "data": {"response_data": {"id": "m9"}}}).encode())
        with mock.patch("urllib.request.urlopen", net):
            self.assertEqual(self.g.send("pat@example.com", "Hi", "Body", thread_id="18f"), "m9")
        r = net.requests[0]
        self.assertTrue(r["url"].endswith("/api/v3.1/tools/execute/GMAIL_REPLY_TO_THREAD"))
        self.assertEqual(r["headers"]["x-api-key"], "main-key")
        self.assertEqual(r["body"]["connected_account_id"], "ca_123")
        self.assertEqual(r["body"]["arguments"], {"thread_id": "18f", "recipient_email": "pat@example.com",
                                                  "message_body": "Body", "is_html": False})

    def test_new_email_when_no_thread(self):
        net = FakeNet(json.dumps({"successful": True, "data": {"id": "m1"}}).encode())
        with mock.patch("urllib.request.urlopen", net):
            self.g.send("pat@example.com", "Following up", "Body")
        self.assertTrue(net.requests[0]["url"].endswith("/GMAIL_SEND_EMAIL"))
        self.assertEqual(net.requests[0]["body"]["arguments"]["subject"], "Following up")

    def test_got_estimate(self):
        net = FakeNet(json.dumps({"successful": True, "data": {"messages": [{"messageId": "x"}]}}).encode(),
                      json.dumps({"successful": True, "data": {"messages": []}}).encode())
        with mock.patch("urllib.request.urlopen", net):
            self.assertTrue(self.g.got_estimate("pat@example.com"))
            self.assertFalse(self.g.got_estimate("eve@example.com"))
        self.assertEqual(net.requests[0]["body"]["arguments"]["query"], "in:sent to:pat@example.com subject:estimate")

    def test_errors_never_show_the_key(self):
        for reply in (urllib.error.HTTPError("u", 401, "no", {}, None),
                      json.dumps({"successful": False, "error": {"message": "Not allowed"}}).encode()):
            with mock.patch("urllib.request.urlopen", FakeNet(reply)):
                with self.assertRaises(clients.EmailError) as cm:
                    self.g.send("pat@example.com", "s", "b")
            self.assertNotIn("main-key", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
