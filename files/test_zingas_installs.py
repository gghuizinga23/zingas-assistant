"""After-install program (F4): from the Completed label to day-3, review, referral and the 6-month check-in."""

import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

import zingas_installs as zi


def utc(y, mo, d, h=15, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)      # 15:00 UTC = 11am Indianapolis


class FakeGmail:
    def __init__(self, msgs, bodies=None):
        self.msgs, self.bodies = msgs, bodies or {}

    def call(self, tool, args):
        assert tool == "GMAIL_FETCH_EMAILS" and "label:Completed" in args["query"]
        return {"messages": self.msgs}

    def body(self, mid):
        return self.bodies.get(mid, "")


class BridgeErr(Exception):
    def __init__(self, status, msg=""):
        super().__init__(msg)
        self.status = status


class FakeBridge:
    def __init__(self):
        self.cards, self.fail = [], None

    def draft(self, payload):
        if self.fail:
            raise self.fail
        self.cards.append(payload)
        return {"id": f"d{len(self.cards)}", "status": "pending"}


SF = {"customer": {"prospectId": "0011234567", "name": "Pat Lee", "email": "pat@example.com",
                   "visits": [{"result": "Sold", "product": "Roman shades"}]}}


def msg(mid, at, subject="Job complete - Pat Lee"):
    return {"messageId": mid, "messageTimestamp": at.isoformat(), "subject": subject, "to": "gerrit@zingashome.com",
            "sender": "install@zingashome.com"}


class Base(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp()
        self.now = utc(2026, 10, 27)
        self.bridge = FakeBridge()
        self.written = []

    def inst(self, msgs, bodies=None, lookup=None, val=None):
        def ask(prompt):
            self.written.append(prompt)
            return val if val is not None else '{"action": "write", "text": "Hi Pat, how are the shades? Gerrit"}'
        return zi.Installs(FakeGmail(msgs, bodies), self.bridge, self.vault, ask_val=ask,
                           lookup=lookup or (lambda p: SF if p == "3175550101" else {"customer": None}),
                           clock=lambda: self.now, notify=lambda t: None)

    def state(self):
        return zi.read_state(self.vault)

    def job(self):
        return list(self.state()["jobs"].values())[0]


class ScanTests(Base):
    def test_known_customer_becomes_a_job_with_the_plan(self):
        i = self.inst([msg("m1", utc(2026, 10, 26))], {"m1": "Customer Pat Lee, phone (317) 555-0101"})
        self.assertEqual(i.scan(), 1)
        j = self.job()
        self.assertEqual((j["name"], j["phone"], j["product"]), ("Pat Lee", "+13175550101", "Roman shades"))
        self.assertEqual(j["touches"]["how"]["due"], zi.iso(utc(2026, 10, 29)))
        self.assertIn("New installs under Completed: Pat Lee", zi.brief_block(self.now, self.vault))
        self.assertEqual(zi.brief_block(self.now, self.vault), "")           # shown once

    def test_unknown_customer_gets_nothing_and_one_brief_line(self):
        i = self.inst([msg("m1", utc(2026, 10, 26), "Job complete $4,200")], {"m1": "call 317-555-9999"})
        self.assertEqual(i.scan(), 0)
        self.assertEqual(self.state()["jobs"], {})
        block = zi.brief_block(self.now, self.vault)
        self.assertIn("could not match", block)
        self.assertNotIn("4,200", block)

    def test_first_look_skips_old_installs(self):
        i = self.inst([msg("m1", utc(2026, 9, 1))], {"m1": "317-555-0101"})
        self.assertEqual(i.scan(), 0)
        self.assertEqual(i.scan(), 0)          # seen: never again

    def test_second_email_for_the_same_job_is_ignored(self):
        i = self.inst([msg("m1", utc(2026, 10, 26)), msg("m2", utc(2026, 10, 27))],
                      {"m1": "317-555-0101", "m2": "317 555 0101"})
        self.assertEqual(i.scan(), 1)

    def test_followup_customer_by_email(self):
        os.makedirs(os.path.join(self.vault, "followups"))
        with open(os.path.join(self.vault, "followups", "state.json"), "w") as fh:
            json.dump({"customers": {"amy@example.com": {"email": "amy@example.com", "name": "Amy Cole",
                                                         "phone": "+13175550102", "product": "Shutters"}}}, fh)
        m = msg("m1", utc(2026, 10, 26))
        m["to"] = "amy@example.com"
        i = self.inst([m])
        self.assertEqual(i.scan(), 1)
        self.assertEqual(self.job()["name"], "Amy Cole")


class CardTests(Base):
    def started(self):
        i = self.inst([msg("m1", utc(2026, 10, 26))], {"m1": "317-555-0101"})
        i.scan()
        return i

    def test_day_three_card_only_when_due_and_in_hours(self):
        i = self.started()
        self.assertEqual(i.cards(), 0)                       # day 1
        self.now = utc(2026, 10, 29, 2)                      # due, but 10pm the night before
        self.assertEqual(i.cards(), 0)
        self.now = utc(2026, 10, 29, 15)
        self.assertEqual(i.cards(), 1)
        card = self.bridge.cards[0]
        self.assertEqual((card["to"], card["category"]), ("+13175550101", "after_install"))
        self.assertIn("Roman shades", self.written[0])
        self.assertIn("Do not ask for a review", self.written[0])
        self.assertEqual(i.cards(), 0)                       # one card at a time

    def test_vals_words_with_a_price_fall_back_to_plain_words(self):
        i = self.started()
        self.now = utc(2026, 10, 29, 15)
        i.ask_val = lambda p: '{"action": "write", "text": "That was $3,000 well spent!"}'
        i.cards()
        self.assertNotIn("$", self.bridge.cards[0]["text"])
        self.assertIn("How are the Roman shades working out?", self.bridge.cards[0]["text"])

    def test_do_not_contact_stops_the_job(self):
        i = self.started()
        self.now = utc(2026, 10, 29, 15)
        self.bridge.fail = BridgeErr(409, "This customer is do-not-contact. No card was made.")
        i.cards()
        self.assertEqual(self.job()["status"], "stopped")

    def sent_how(self, i):
        self.now = utc(2026, 10, 29, 15)
        i.cards()
        zi.note_outcome({"draft_id": "d1", "category": "after_install", "status": "sent",
                         "sent_at": zi.iso(self.now), "phone": "+13175550101"}, self.vault)

    def test_happy_answer_with_link_makes_the_reply_a_review_ask_then_referral_a_week_later(self):
        zi.save_settings({"review_link": "https://g.page/r/zingas/review", "referral": "a gift card"}, self.vault)
        i = self.started()
        self.sent_how(i)
        ctx = zi.reply_context("(317) 555-0101", self.vault, self.now + timedelta(hours=2))
        self.assertIn("https://g.page/r/zingas/review", ctx)
        kind = zi.record_answer("+13175550101", "happy", "So glad! Review: https://g.page/r/zingas/review", self.vault)
        self.assertEqual(kind, "review_ask")
        self.assertEqual(zi.reply_context("3175550101", self.vault), "")        # answered once
        zi.note_outcome({"draft_id": "x9", "category": "review_ask", "status": "sent", "phone": "+13175550101",
                         "sent_at": zi.iso(self.now)}, self.vault)
        self.now += timedelta(days=6)
        self.assertEqual(i.cards(), 0)
        self.now += timedelta(days=1)
        self.assertEqual(i.cards(), 1)
        self.assertEqual(self.bridge.cards[-1]["category"], "referral_ask")
        self.assertIn("a gift card", self.written[-1])

    def test_happy_without_link_waits_and_asks_gerrit_in_the_brief(self):
        i = self.started()
        self.sent_how(i)
        self.assertNotIn("https://", zi.reply_context("3175550101", self.vault, self.now))
        self.assertIsNone(zi.record_answer("3175550101", "happy", "Glad you love them!", self.vault))
        self.assertIn("Send Val your Google review link", zi.brief_block(self.now, self.vault))
        self.assertEqual(i.cards(), 0)
        zi.save_settings({"review_link": "https://g.page/r/zingas/review"}, self.vault)
        i.ask_val = lambda p: '{"action": "write", "text": "Thanks Pat! https://g.page/r/zingas/review Gerrit"}'
        self.assertEqual(i.cards(), 1)
        self.assertEqual(self.bridge.cards[-1]["category"], "review_ask")

    def test_review_card_without_the_link_is_replaced_by_plain_words(self):
        zi.save_settings({"review_link": "https://g.page/r/zingas/review"}, self.vault)
        i = self.started()
        self.sent_how(i)
        zi.record_answer("3175550101", "happy", "Thanks!", self.vault)          # the reply had no link
        i.ask_val = lambda p: '{"action": "write", "text": "Thanks Pat, a review would help! Gerrit"}'
        i.cards()
        self.assertIn("https://g.page/r/zingas/review", self.bridge.cards[-1]["text"])

    def test_problem_means_no_review_and_no_referral(self):
        zi.save_settings({"review_link": "https://g.page/r/zingas/review"}, self.vault)
        i = self.started()
        self.sent_how(i)
        self.assertIsNone(zi.record_answer("3175550101", "problem", "", self.vault))
        t = self.job()["touches"]
        self.assertEqual((t["review"]["state"], t["referral"]["state"]), ("skipped", "skipped"))
        self.assertIn("problem after the install", zi.brief_block(self.now, self.vault))
        self.now += timedelta(days=30)
        self.assertEqual(i.cards(), 0)

    def test_no_answer_in_a_week_means_no_review_ask(self):
        zi.save_settings({"review_link": "https://g.page/r/zingas/review"}, self.vault)
        i = self.started()
        self.sent_how(i)
        self.now += timedelta(days=8)
        self.assertEqual(i.cards(), 0)
        self.assertEqual(self.job()["verdict"], "quiet")

    def test_skip_on_day_three_ends_the_program(self):
        i = self.started()
        self.now = utc(2026, 10, 29, 15)
        i.cards()
        zi.note_outcome({"draft_id": "d1", "category": "after_install", "status": "skipped"}, self.vault)
        self.assertEqual(self.job()["status"], "stopped")

    def test_six_month_check_in_and_winter_waits_for_march(self):
        self.assertEqual(zi.rooms_day(utc(2026, 3, 1)).astimezone(zi.TZ).date(), date(2026, 8, 30))
        self.assertEqual(zi.rooms_day(utc(2026, 6, 1)).astimezone(zi.TZ).date(), date(2027, 3, 15))
        self.assertEqual(zi.rooms_day(utc(2026, 8, 1)).astimezone(zi.TZ).date(), date(2027, 3, 15))

    def test_rooms_card_after_quiet(self):
        i = self.started()
        self.sent_how(i)
        self.now = zi.parse_iso(self.job()["touches"]["rooms"]["due"]) + timedelta(days=1)
        self.now = self.now.replace(hour=15)
        self.assertEqual(i.cards(), 1)
        self.assertEqual(self.bridge.cards[-1]["category"], "install_checkin")


class CommandTests(unittest.TestCase):
    def test_settings_refuse_amounts_and_bad_links(self):
        vault = tempfile.mkdtemp()
        old = zi.VAULT
        zi.VAULT = vault
        try:
            self.assertEqual(zi.main(["set", "review-link", "g.page/r/x"]), 1)
            self.assertEqual(zi.main(["set", "referral", "a $50 gift card"]), 1)
            self.assertEqual(zi.main(["set", "review-link", "https://g.page/r/zingas/review"]), 0)
            self.assertEqual(zi.settings(vault)["review_link"], "https://g.page/r/zingas/review")
        finally:
            zi.VAULT = old

    def test_add_only_known_customers(self):
        vault = tempfile.mkdtemp()
        self.assertIn("does not know", zi.add_job("317-555-9999", date(2026, 10, 20), vault, lambda p: None))
        self.assertIn("Started", zi.add_job("317-555-0101", date(2026, 10, 20), vault, lambda p: SF))
        self.assertIn("already", zi.add_job("317-555-0101", date(2026, 10, 21), vault, lambda p: SF))


if __name__ == "__main__":
    unittest.main()
