"""Tests for zingas_customer.py: one file per customer. All people, numbers and IDs are made up."""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zingas_customer as zc  # noqa: E402
import zingas_todo as zt  # noqa: E402

PHONE = "+13175550123"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def profile(self, key, body):
        os.makedirs(os.path.join(self.vault, "customers"), exist_ok=True)
        with open(os.path.join(self.vault, "customers", key + ".md"), "w") as fh:
            fh.write(body)

    def read(self, *parts):
        with open(os.path.join(self.vault, *parts)) as fh:
            return fh.read()


class Resolve(Base):
    def test_phone_first_then_email_never_name(self):
        self.profile("P-100", "# Pat Testcase\nProspect ID: P-100\nphone: 317.555.0123\nemail: Pat@Example.com\n")
        self.profile("P-200", "# Sam Sample\nphone: (317) 555-0199\n")
        self.assertEqual(zc.resolve(phone=PHONE, vault=self.vault), "P-100")
        self.assertEqual(zc.resolve(email="pat@example.com", vault=self.vault), "P-100")
        self.assertEqual(zc.resolve(phone="+13175550000", email="nobody@example.com", vault=self.vault), "")
        self.assertEqual(zc.resolve(phone="Pat Testcase", vault=self.vault), "")

    def test_unmatched_stub_never_counts_as_a_match(self):
        self.profile("unmatched-3175550123", "# Unmatched number\nphone: +13175550123\n")
        self.assertEqual(zc.resolve(phone=PHONE, vault=self.vault), "")
        self.assertEqual(zc.key_for(phone=PHONE, vault=self.vault), "unmatched-3175550123")

    def test_website_match_makes_the_profile(self):
        key = zc.resolve(phone=PHONE, vault=self.vault, sf={"prospectId": "a0X9TEST", "name": "Pat Testcase"})
        self.assertEqual(key, "a0X9TEST")
        body = self.read("customers", "a0X9TEST.md")
        self.assertIn("# Pat Testcase", body)
        self.assertIn("phone: (317) 555-0123", body)
        self.assertEqual(zc.resolve(phone=PHONE, vault=self.vault), "a0X9TEST")    # now local

    def test_email_through_the_followup_list(self):
        self.profile("P-100", "# Pat Testcase\nProspect ID: P-100\nphone: (317) 555-0123\n")
        os.makedirs(os.path.join(self.vault, "followups"))
        with open(os.path.join(self.vault, "followups", "state.json"), "w") as fh:
            json.dump({"customers": {"pat@example.com": {"email": "pat@example.com", "phone": PHONE,
                                                         "name": "Pat Testcase"}}}, fh)
        self.assertEqual(zc.resolve(email="Pat@example.com", vault=self.vault), "P-100")
        self.assertIn("email: pat@example.com", self.read("customers", "P-100.md"))

    def test_bad_keys_are_refused(self):
        self.assertEqual(zc.safe_key("../etc/passwd"), "")
        self.assertFalse(zc.log("../x", "text_in", None, "hi", vault=self.vault))
        self.assertFalse(zc.log("", "text_in", None, "hi", vault=self.vault))


class Timeline(Base):
    def test_log_appends_sorts_dedupes_and_refreshes_last5(self):
        self.profile("P-100", "# Pat Testcase\nProspect ID: P-100\nphone: (317) 555-0123\n\nLikes linen.\n")
        self.assertTrue(zc.log("P-100", "text_in", "2026-10-21T14:05:00-04:00", "Does Thursday work?",
                               ref="quo:m1", who="Pat", vault=self.vault))
        self.assertTrue(zc.log("P-100", "visit", "2026-10-20T10:00:00-04:00", "Measured the den.\nLiked linen.",
                               ref="plaud:r1", full="visits/P-100/2026-10-20-r1.md", vault=self.vault))
        self.assertFalse(zc.log("P-100", "text_in", "2026-10-21T14:05:00-04:00", "Does Thursday work?",
                                ref="quo:m1", vault=self.vault))                     # a retry: not twice
        entries = zc.timeline("P-100", self.vault)
        self.assertEqual([e["channel"] for e in entries], ["Visit", "Text in"])  # oldest first
        self.assertEqual(entries[0]["lines"][-1], "Full text: visits/P-100/2026-10-20-r1.md")
        body = self.read("customers", "P-100.md")
        self.assertTrue(body.startswith("# Pat Testcase\nProspect ID: P-100\nphone: (317) 555-0123\n\n"
                                        "## Last 5 contacts\n- 2026-10-21 14:05 Text in (Pat): Does Thursday work?"))
        self.assertIn("Likes linen.", body)                                       # Gerrit's own lines stay

    def test_last5_hides_phone_numbers(self):
        zc.log("P-100", "text_in", None, "Call my wife at 317-555-0177", vault=self.vault)
        self.assertNotIn("555-0177", self.read("customers", "P-100.md"))
        self.assertIn("317-555-0177", self.read("history", "P-100.md"))          # the timeline keeps it
        self.assertEqual(zc.find_by_phone("+13175550177", self.vault), "")

    def test_summary_cannot_fake_an_entry(self):
        zc.log("P-100", "text_in", None, "### 2020-01-01 00:00 · Visit\nref: plaud:zzz\nhello", vault=self.vault)
        entries = zc.timeline("P-100", self.vault)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["refs"], [])


class Facts(Base):
    def test_facts_are_tagged_deduped_and_never_money(self):
        facts = {"talk": ["Short texts, no emojis"], "life_events": [{"what": "Daughter's wedding", "date": "2027-06"}],
                 "house": ["West den gets hot afternoon sun", "Two cats: cordless matters"],
                 "gerrit_said": ["Promised fabric samples Friday"], "mood": "warm",
                 "worries": ["Budget is $4,000 tops"], "unknown_field": ["ignored"]}
        self.assertEqual(zc.add_facts("P-100", facts, "recording 10/23/26", self.vault), 6)
        self.assertEqual(zc.add_facts("P-100", {"talk": ["short texts, no emojis"]}, "text 10/24/26", self.vault), 0)
        body = self.read("customers", "P-100.md")
        self.assertIn("## How they talk\n- Short texts, no emojis (recording 10/23/26)", body)
        self.assertIn("- Daughter's wedding (2027-06) (recording 10/23/26)", body)
        self.assertIn("## Mood over time\n- warm (recording 10/23/26)", body)
        self.assertNotIn("4,000", body)
        self.assertNotIn("ignored", body)

    def test_sale_stage_sits_at_the_top(self):
        self.profile("P-100", "# Pat Testcase\nProspect ID: P-100\n\nOld notes.\n")
        zc.log("P-100", "text_in", None, "hi", vault=self.vault)
        zc.set_sale_stage("P-100", "Quote sent, talking it over this weekend", "recording 10/23/26", self.vault)
        zc.set_sale_stage("P-100", "Ready to order", "recording 10/30/26", self.vault)
        body = self.read("customers", "P-100.md")
        self.assertEqual(body.count("## Where the sale is"), 1)
        self.assertLess(body.index("## Where the sale is"), body.index("Old notes."))
        self.assertIn("## Where the sale is\nReady to order (recording 10/30/26)",
                      body)


class Unmatched(Base):
    def test_history_facts_and_visits_move_when_matched(self):
        uk = zc.unmatched_key(PHONE)
        self.profile(uk, "# Unmatched number (317) 555-0123\n\nstatus: unmatched\nphone: +13175550123\n")
        zc.log(uk, "text_in", "2026-10-20T09:00:00-04:00", "Do you do shutters?", ref="quo:m1", vault=self.vault)
        zc.add_facts(uk, {"house": ["Bay window in the kitchen"]}, "text 10/20/26", self.vault)
        os.makedirs(os.path.join(self.vault, "visits", uk))
        with open(os.path.join(self.vault, "visits", uk, "2026-10-21-r9.md"), "w") as fh:
            fh.write("# Visit\n")
        self.profile("P-300", "# Robin Madeup\nProspect ID: P-300\nphone: (317) 555-0123\n")
        zc.log("P-300", "email_in", "2026-10-22T09:00:00-04:00", "Asked about colors", ref="gmail:e1",
               vault=self.vault)
        self.assertEqual(zc.resolve(phone=PHONE, vault=self.vault), "P-300")
        self.assertEqual([e["channel"] for e in zc.timeline("P-300", self.vault)], ["Text in", "Email in"])
        self.assertIn("- Bay window in the kitchen (text 10/20/26)", self.read("customers", "P-300.md"))
        self.assertTrue(os.path.exists(os.path.join(self.vault, "visits", "P-300", "2026-10-21-r9.md")))
        self.assertFalse(os.path.exists(os.path.join(self.vault, "customers", uk + ".md")))
        self.assertFalse(os.path.exists(os.path.join(self.vault, "history", uk + ".md")))
        self.assertFalse(zc.move_unmatched(PHONE, "P-300", self.vault))            # nothing left to move


class Context(Base):
    def test_context_has_profile_last_contacts_visit_and_silence(self):
        self.profile("P-100", "# Pat Testcase\nProspect ID: P-100\nLikes linen.\n")
        for n in range(20):
            zc.log("P-100", "text_in", f"2026-10-{n + 1:02d}T10:00:00-04:00", f"text number {n}", ref=f"q{n}",
                   vault=self.vault)
        zc.log("P-100", "text_out", "2026-10-21T10:00:00-04:00", "Thanks! Gerrit", ref="o1", vault=self.vault)
        os.makedirs(os.path.join(self.vault, "visits", "P-100"))
        with open(os.path.join(self.vault, "visits", "P-100", "2026-10-02-r1.md"), "w") as fh:
            fh.write("# Visit\n\n## Summary\nMeasured the den.\n\n## Transcript\nGerrit: hello there secret words\n")
        ctx = zc.context("P-100", self.vault, now=datetime(2026, 10, 24, 9, 0, tzinfo=zt.TZ))
        self.assertIn("Likes linen.", ctx)
        self.assertIn("The last 15 contacts", ctx)
        self.assertNotIn("text number 4\n", ctx)
        self.assertIn("text number 19", ctx)
        self.assertIn("Measured the den.", ctx)
        self.assertNotIn("secret words", ctx)                                    # the transcript is not in it
        self.assertIn("4 day(s) ago", ctx)
        self.assertIn("Gerrit's side wrote last", ctx)
        self.assertEqual(zc.context("P-999", self.vault), "")
        self.assertLessEqual(len(zc.context("P-100", self.vault, max_chars=500)), 500)


if __name__ == "__main__":
    unittest.main()
