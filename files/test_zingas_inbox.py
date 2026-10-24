"""Tests for zingas_inbox.py with a fake Gmail and a fake Val. No real email."""

import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock

import zingas_inbox as zi
import zingas_todo as zt


class FakeGmail:
    def __init__(self):
        self.mail, self.bodies, self.broken, self.sent_mail = [], {}, set(), []

    def sent(self, after_epoch, limit=25):
        return [m for m in self.sent_mail if m["_ts"] >= after_epoch]

    def recent(self, after_epoch, limit=25):
        return [m for m in self.mail if m["_ts"] >= after_epoch]

    def body(self, message_id):
        if message_id in self.broken:
            raise zi.GmailError("nope")
        return self.bodies.get(message_id, "")


def email(mid, ts, sender="Pat Lee <pat@example.com>", subject="Shades", labels=("INBOX",), thread=None):
    return {"messageId": mid, "_ts": ts, "messageTimestamp": str(ts), "sender": sender, "subject": subject,
            "labelIds": list(labels), "threadId": thread or "th-" + mid,
            "display_url": f"https://mail.google.com/mail/u/0/#inbox/{mid}", "preview": {"body": "preview text"}}


class InboxTests(unittest.TestCase):
    def setUp(self):
        d = self.vault = tempfile.mkdtemp()
        self.gmail, self.todo, self.sent, self.prompts = FakeGmail(), zt.TodoList(d), [], []
        self.answer = lambda ids: {"results": [{"id": i, "action": "add", "task": "Call back about shades",
                                                "priority": "today"} for i in ids]}
        self.now = 1_800_000_000
        day = datetime(2026, 10, 21, 10, 0, tzinfo=zt.TZ)
        patcher = mock.patch.object(zt, "quiet_hours", lambda at=None: day.hour < 8)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.inbox = zi.Inbox(self.gmail, self.todo, ask_val=self._val, notify=self.sent.append,
                              state_path=os.path.join(d, "state.json"), clock=lambda: self.now, skill_path="/nope")

    def _val(self, prompt):
        self.prompts.append(prompt)
        ids = [line.split('"')[1] for line in prompt.splitlines() if line.startswith("<item id=")]
        return json.dumps(self.answer(ids))

    def test_first_run_only_takes_a_baseline(self):
        self.gmail.mail = [email("old1", self.now - 60)]
        self.assertEqual(self.inbox.once(), {"baseline": 1})
        self.assertEqual(self.todo.open_items(), [])
        self.assertEqual(self.prompts, [])
        self.now += 120
        self.inbox.once()
        self.assertEqual(self.todo.open_items(), [])      # the old email isn't judged later either

    def test_new_email_becomes_a_task_and_gerrit_is_told(self):
        self.inbox.once()
        self.gmail.mail = [email("m1", self.now + 30)]
        self.gmail.bodies["m1"] = "Can you call me about the motorized shades?"
        self.now += 120
        done = self.inbox.once()
        self.assertEqual(done["added"], 1)
        item = self.todo.open_items()[0]
        self.assertEqual((item["task"], item["who"], item["source"], item["ref"]),
                         ("Call back about shades", "Pat Lee", "email", "gmail:th-m1"))
        self.assertTrue(item["link"].startswith("https://mail.google.com/"))
        self.assertIn("motorized shades", self.prompts[0])
        self.assertIn("📝 New task on your to-do list:\n🟡 1. Pat Lee: Call back about shades", self.sent[0])
        self.now += 120
        self.assertEqual(self.inbox.once()["new"], 0)     # never twice

    def test_promos_spam_and_no_reply_never_reach_val(self):
        self.inbox.once()
        self.gmail.mail = [email("p", self.now + 1, labels=("CATEGORY_PROMOTIONS",)),
                           email("s", self.now + 2, labels=("SPAM",)),
                           email("n", self.now + 3, sender="Salesforce <noreply@salesforce.com>"),
                           email("real", self.now + 4, labels=("Label_7",))]
        self.now += 120
        done = self.inbox.once()
        self.assertEqual((done["skipped"], done["added"]), (3, 1))
        self.assertEqual(len(self.prompts), 1)
        self.assertIn('<item id="real"', self.prompts[0])
        self.assertIn("Folder/label: Label_7", self.prompts[0])
        self.assertNotIn('<item id="p"', self.prompts[0])

    def test_skips_and_updates_send_no_note(self):
        self.inbox.once()
        self.todo.add("Answer Pat about Thursday", ref="gmail:th-x")
        self.gmail.mail = [email("a", self.now + 1), email("b", self.now + 2)]
        self.answer = lambda ids: {"results": [{"id": "a", "action": "skip"},
                                               {"id": "b", "action": "update", "update_number": 1,
                                                "task": "Answer Pat about Thursday at 2", "priority": "now"}]}
        self.now += 120
        done = self.inbox.once()
        self.assertEqual((done["skipped"], done["updated"], done["added"]), (1, 1, 0))
        self.assertEqual([(i["task"], i["priority"]) for i in self.todo.open_items()],
                         [("Answer Pat about Thursday at 2", "now")])
        self.assertEqual(self.sent, [])

    def test_val_fails_three_times_then_a_plain_task(self):
        self.inbox.once()
        self.gmail.mail = [email("m1", self.now + 1, subject="Contract question")]
        self.answer = lambda ids: {"results": []}
        for _ in range(2):
            self.now += 120
            self.assertEqual(self.inbox.once()["retry"], 1)
            self.assertEqual(self.todo.open_items(), [])
        self.now += 120
        self.inbox.once()
        item = self.todo.open_items()[0]
        self.assertEqual((item["task"], item["priority"]), ("Read this email: Contract question", "today"))

    def test_unreadable_body_uses_the_preview(self):
        self.inbox.once()
        self.gmail.mail = [email("m1", self.now + 1)]
        self.gmail.broken.add("m1")
        self.now += 120
        self.inbox.once()
        self.assertIn("preview text", self.prompts[0])

    def test_a_new_task_alerts_gerrit_even_in_quiet_hours(self):
        """Gerrit's rule (2026-10-23): every new to-do alerts him right away, any hour."""
        self.inbox.once()
        self.gmail.mail = [email("m1", self.now + 1)]
        self.now += 120
        with mock.patch.object(zt, "quiet_hours", lambda at=None: True):
            self.inbox.once()
        self.assertEqual(len(self.todo.open_items()), 1)
        self.assertEqual(len(self.sent), 1)

    def customer(self):
        os.makedirs(os.path.join(self.vault, "customers"), exist_ok=True)
        with open(os.path.join(self.vault, "customers", "P-100.md"), "w") as fh:
            fh.write("# Pat Lee\nProspect ID: P-100\nemail: pat@example.com\nLikes linen.\n")

    def test_a_customer_email_is_judged_with_the_file_and_logged(self):
        import zingas_customer as zc
        self.customer()
        self.inbox.once()
        self.gmail.mail = [email("m1", self.now + 30, subject="Colors")]
        self.gmail.bodies["m1"] = "We're back from Florida the 15th. Can we see the gray samples?"
        self.answer = lambda ids: {"results": [{"id": i, "action": "add", "task": "Bring the gray samples",
                                                "priority": "today", "summary": "Pat asks to see gray samples.",
                                                "facts": {"life_events": [{"what": "Back from Florida",
                                                                           "date": "2026-11-15"}]}}
                                               for i in ids]}
        self.now += 120
        self.inbox.once()
        p = self.prompts[0]
        self.assertIn('<item id="m1" kind="email" customer="yes">', p)
        self.assertIn("Likes linen.", p)
        entry = zc.timeline("P-100", self.vault)[-1]
        self.assertEqual((entry["channel"], entry["lines"], entry["refs"]),
                         ("Email in", ["Pat asks to see gray samples."], ["gmail:m1"]))
        with open(os.path.join(self.vault, "customers", "P-100.md")) as fh:
            self.assertIn("- Back from Florida (2026-11-15) (email ", fh.read())

    def test_strangers_and_office_mail_are_not_logged(self):
        self.customer()
        self.inbox.once()
        self.gmail.mail = [email("m1", self.now + 30, sender="Beth <beth@zingashome.com>"),
                           email("m2", self.now + 31, sender="Vendor <sales@vendor.example>")]
        self.now += 120
        self.inbox.once()
        self.assertNotIn('customer="yes"', self.prompts[0])
        self.assertFalse(os.path.exists(os.path.join(self.vault, "history", "P-100.md")))

    def test_gerrits_sent_email_to_a_customer_is_logged_once(self):
        import zingas_customer as zc
        self.customer()
        self.inbox.once()
        self.gmail.sent_mail = [dict(email("s1", self.now + 10, subject="Your quote"), to="Pat <PAT@example.com>",
                                     preview={"body": "Here is your quote. Gerrit"}),
                                dict(email("s2", self.now + 11, subject="Office"), to="beth@zingashome.com")]
        self.now += 120
        self.inbox.once()
        self.now += 120
        self.inbox.once()
        got = [(e["channel"], e["lines"]) for e in zc.timeline("P-100", self.vault)]
        self.assertEqual(got, [("Email out", ["Subject: Your quote", "Here is your quote. Gerrit"])])


class Helpers(unittest.TestCase):
    def test_names_and_labels(self):
        self.assertEqual(zi.name_of('"Beth, Payments" <beth@zingashome.com>'), "Beth, Payments")
        self.assertEqual(zi.name_of("pat@example.com"), "pat@example.com")
        self.assertEqual(zi.label_of({"labelIds": ["INBOX", "UNREAD"]}), "")
        self.assertEqual(zi.label_of({"labelIds": ["Label_3"]}), "Label_3")
        self.assertFalse(zi.worth_a_look({"sender": "Do-Not-Reply <x@y.com>"}))
        self.assertTrue(zi.worth_a_look({"sender": "Pat <pat@x.com>", "labelIds": ["INBOX"]}))


if __name__ == "__main__":
    unittest.main()
