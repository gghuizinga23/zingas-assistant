"""Tests for zingas_followups.py and followup_wording.py. Every name, email and
phone here is made up. Run: python3 -m unittest files/test_zingas_followups.py"""

import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quo-bridge"))

import followup_wording as fw  # noqa: E402
import send_gate  # noqa: E402
import zingas_followups as zf  # noqa: E402

TZ = zf.TZ


def at(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


def z(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def appt_msg(mid, when, names, phone="(317) 555-0142", city="Carmel, IN 46032", kind="", interest="Screens"):
    subject = f"{kind}Appt on {when:%-m/%-d/%Y} at {when:%-I:%M %p} with {names}"
    text = (f"Date: {when:%m/%d/%Y}\nTime: {when:%-I:%M %p}\nDuration: 90 min\nInterest(s): {interest}\n"
            f"Rep 1: Gerrit Huizinga\nName(s): {names}\nAddress: 1 Test Lane\n{city}\nPhone: {phone}\n")
    return {"messageId": mid, "subject": subject, "messageText": text, "messageTimestamp": z(when - timedelta(days=3)),
            "sender": "appointments@zingashome.com"}


class FakeGmail:
    def __init__(self):
        self.appts, self.estimates, self.attach = [], [], {}
        self.proposals, self.bodies = [], {}
        self.payment, self.contracts, self.completed = [], [], []
        self.inbox, self.sent = [], []
        self.queries = []

    def add_estimate(self, mid, to, when, pdf, subject="Zinga's Screens Estimate", thread="t" + "1" * 8):
        self.estimates.append({"messageId": mid, "threadId": thread, "to": to, "subject": subject,
                               "messageTimestamp": z(when)})
        self.attach[mid] = [{"filename": pdf, "mimeType": "application/pdf"}]

    def add_proposal(self, mid, to, when, first="Pat", options=("Track screens", "Cable-guided screens"),
                     thread="p" + "1" * 8, subject="Your proposal from Zinga's"):
        """The new estimator's email (app proposalEmail): a link, no PDF, each option with its price."""
        self.proposals.append({"messageId": mid, "threadId": thread, "to": to, "subject": subject,
                               "messageTimestamp": z(when)})
        lines = "\n".join(f"{o}: $89/mo with Test Bank, or $4,250 total" for o in options)
        self.bodies[mid] = (f"Hi {first},\n\nYour Zinga's proposal is ready:\nhttps://example.com/p/abc\n\n{lines}\n\n"
                            "Pricing is held until Nov 30.\n\nGerrit Huizinga\nZinga's · 317-555-0100")

    def call(self, tool, args):
        if tool == "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID":
            return {"attachmentList": self.attach.get(args["message_id"], []),
                    "messageText": self.bodies.get(args["message_id"], "")}
        q = args["query"]
        self.queries.append(q)
        if q.startswith("from:appointments@"):
            msgs = self.appts
        elif q.startswith("in:sent subject:estimate"):
            msgs = self.estimates
        elif q.startswith('in:sent subject:"your proposal from"'):
            msgs = self.proposals
        elif "payment link" in q:
            msgs = self.payment
        elif q.startswith("in:sent to:(payments@"):
            msgs = self.contracts
        elif q.startswith("label:customers-completed"):
            msgs = self.completed
        elif q.startswith("from:("):
            msgs = [m for m in self.inbox if m["sender"] in q]
        elif q.startswith("in:sent to:("):
            msgs = [m for m in self.sent if m["to"] in q]
        else:
            msgs = []
        return {"messages": list(msgs)}


class FakeBridge:
    def __init__(self):
        self.submitted, self.paused, self.acked, self.out, self.texts = [], [], [], [], {}

    def submit(self, day, items):
        self.submitted.append((day, items))
        return {"items": [{"customer_key": i["customer_key"], "touch": i["touch"], "id": "f" + str(n),
                           "status": "planned"} for n, i in enumerate(items)]}

    def outcomes(self):
        out, self.out = self.out, []
        return out

    def ack(self, ids):
        self.acked += ids

    def pause(self, phone="", email="", reason=""):
        self.paused.append((phone, email, reason))
        return 1

    def contacts(self, phones, thread_for=None):
        return {p: self.texts.get(p, {}) for p in phones}


# ------------------------------------------------------------ wording

class WordingTests(unittest.TestCase):
    def test_every_wording_follows_the_rules(self):
        for touch in fw.TOUCHES:
            for product in ("", "screens", "pergola", "blinds and shades", "awning", "shutters"):
                for day in (date(2026, 1, 5), date(2026, 4, 5), date(2026, 7, 5), date(2026, 10, 5)):
                    w = fw.write(touch, "Pat", product, day)
                    for part in ("text", "email_body", "email_subject"):
                        self.assertEqual(send_gate.money_terms(w[part]), [], (touch, product, part))
                        self.assertNotIn("—", w[part])
                        self.assertNotIn("–", w[part])
                    self.assertLess(len(w["text"]), 700)
                    self.assertTrue(w["text"].startswith("Hey Pat!"))
                    self.assertTrue(w["email_body"].startswith("Hi Pat,"))

    def test_no_name(self):
        w = fw.write("48 hours", "", "", date(2026, 10, 20))
        self.assertTrue(w["text"].startswith("Hey there!"))
        self.assertIn("the estimate", w["text"])

    def test_rotation_and_close(self):
        kinds = [fw.kind_of(t) for t in fw.TOUCHES]
        self.assertEqual(kinds[:2], ["48 hours", "7 days"])
        self.assertEqual(kinds[2:6], list(fw.ROTATION))
        self.assertEqual(kinds[-1], "close")
        self.assertIn("close your file", fw.write("day 90", "Pat", "screens", date(2026, 10, 1))["text"])


# ------------------------------------------------------------ reading

class ReadingTests(unittest.TestCase):
    def test_appointment(self):
        a = zf.parse_appointment(appt_msg("a1", at(2026, 10, 19, 18), "Pat and Sam Testerson"))
        self.assertEqual(a["firsts"], ["pat", "sam"])
        self.assertEqual(a["lasts"], ["testerson"])
        self.assertEqual(a["phone"], "+13175550142")
        self.assertEqual(zf.parse_iso(a["at"]), at(2026, 10, 19, 18))
        self.assertEqual(a["time_zone"], "America/Indiana/Indianapolis")

    def test_two_phones_takes_the_first(self):
        m = appt_msg("a4", at(2026, 10, 19, 9), "Kim Example", phone="(317) 555-0142, (317) 555-0199")
        self.assertEqual(zf.parse_appointment(m)["phone"], "+13175550142")
        self.assertEqual(zf.first_phone("317.555.0142"), "+13175550142")
        self.assertEqual(zf.first_phone("none"), "")

    def test_appointment_with_age_and_other_state(self):
        a = zf.parse_appointment(appt_msg("a2", at(2026, 10, 19, 9), "Kim Example - 55", city="Dayton, OH 45402"))
        self.assertEqual((a["firsts"], a["lasts"], a["name"]), (["kim"], ["example"], "Kim Example"))
        self.assertEqual(a["time_zone"], "America/New_York")

    def test_canceled_is_ignored(self):
        m = appt_msg("a3", at(2026, 10, 19, 9), "Kim Example", kind="CANCELED: ")
        self.assertIsNone(zf.parse_appointment(m))

    def test_product(self):
        self.assertEqual(zf.product_of("Zinga's Blinds Shades Estimate"), "blinds and shades")
        self.assertEqual(zf.product_of("Zinga’s Pergola Estimates"), "pergola")
        self.assertEqual(zf.product_of("Estimate"), "")

    def test_external_emails(self):
        self.assertEqual(zf.external_emails("Pat <Pat@Example.com>, office@zingashome.com"), ["pat@example.com"])

    def test_match_picks_the_named_visit_in_the_window(self):
        appts = [zf.parse_appointment(m) for m in (
            appt_msg("a1", at(2026, 10, 19, 18), "Pat Testerson"),
            appt_msg("a2", at(2026, 10, 19, 15), "Lee Other"),
            appt_msg("a3", at(2026, 9, 1, 15), "Pat Testerson"),          # too long before
        )]
        est = {"email": "pt1980@example.com", "sent_at": z(at(2026, 10, 20, 10)), "pdfs": ["PatTestersonEstimate.pdf"]}
        self.assertEqual(zf.match_appointment(est, appts)["msg_id"], "a1")
        est["pdfs"] = ["Estimate.pdf"]
        self.assertIsNone(zf.match_appointment(est, appts))              # nothing names them
        est["email"] = "testerson.family@example.com"
        self.assertEqual(zf.match_appointment(est, appts)["msg_id"], "a1")

    def test_schedule_starts_at_the_visit_inside_8_to_8(self):
        a = zf.parse_appointment(appt_msg("a1", at(2026, 10, 19, 19, 30), "Pat Testerson"))
        est = {"email": "pat@example.com", "sent_at": z(at(2026, 10, 20, 10)), "msg_id": "e1", "pdfs": []}
        c = zf.new_customer(est, a, at(2026, 10, 20, 11))
        self.assertEqual(zf.parse_iso(c["touches"]["48 hours"]["due"]), at(2026, 10, 21, 19, 30))
        self.assertEqual(len(c["touches"]), 10)
        self.assertEqual(c["first"], "Pat")
        late = zf.window(at(2026, 10, 21, 20, 15), "America/Indiana/Indianapolis")
        early = zf.window(at(2026, 10, 21, 6, 0), "America/Indiana/Indianapolis")
        self.assertEqual((late, early), (at(2026, 10, 22, 8), at(2026, 10, 21, 8)))

    def test_written_touch_is_checked(self):
        self.assertIsNone(zf.parse_written("no json here"))
        self.assertIsNone(zf.parse_written('{"action": "write", "text": "", "email_body": "x"}'))
        self.assertEqual(zf.parse_written('ok {"action": "stop", "why": "they bought"}')["why"], "they bought")
        got = zf.parse_written('{"action": "write", "text": "Hey Pat — quick one", "email_body": "Hi Pat,"}')
        self.assertEqual(got["text"], "Hey Pat , quick one")


# ------------------------------------------------------------ the program

class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = at(2026, 10, 20, 11)
        self.g = FakeGmail()
        self.b = FakeBridge()
        self.written = []
        self.g.appts.append(appt_msg("a1", at(2026, 10, 19, 18), "Pat and Sam Testerson"))
        self.g.add_estimate("e1", "Pat <pat.testerson@example.com>", at(2026, 10, 20, 10), "PatTestersonEstimate.pdf")

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, live=False):
        if live:
            os.makedirs(os.path.join(self.tmp.name, "followups"), exist_ok=True)
            open(os.path.join(self.tmp.name, "followups", "LIVE"), "w").close()
        return zf.Followups(self.g, self.b, vault=self.tmp.name, clock=lambda: self.now,
                            writer=lambda prompt: self.written.append(prompt) or self.reply)

    def customer(self, f):
        return f.st["customers"]["pat.testerson@example.com"]

    def test_scan_adds_a_customer_once(self):
        f = self.make()
        self.assertEqual(f.scan()["new_customers"], 1)
        f.st["last_scan"] = ""
        self.assertEqual(f.scan()["new_customers"], 0)
        c = self.customer(f)
        self.assertEqual((c["status"], c["phone"], c["first"]), ("active", "+13175550142", "Pat"))
        self.assertEqual(c["product"], "screens")

    def test_estimator_proposal_is_found_and_matched_without_a_pdf(self):
        self.g.estimates.clear()
        self.g.appts.append(appt_msg("a2", at(2026, 10, 20, 9), "Kim Example", phone="(317) 555-0177"))
        self.g.add_proposal("p1", "Kim <kimberly.e@example.com>", at(2026, 10, 20, 10, 30), first="Kim")
        f = self.make()
        found = f.scan()
        self.assertEqual(found["new_customers"], 1)
        c = f.st["customers"]["kimberly.e@example.com"]
        self.assertEqual(c["status"], "active")
        self.assertEqual(c["est_kind"], "proposal")
        self.assertEqual(c["first"], "Kim")
        self.assertEqual(c["phone"], "+13175550177")
        self.assertEqual(c["quoted"], ["Track screens", "Cable-guided screens"])
        self.assertEqual(c["product"], "screens")          # from the appointment's interest
        self.assertNotIn("$", json.dumps(c))
        self.assertEqual(f.scan()["new_customers"], 0)      # seen once

    def test_proposal_first_name_alone_needs_the_same_day(self):
        self.g.estimates.clear()
        self.g.appts.append(appt_msg("a2", at(2026, 10, 14, 9), "Kim Example"))
        self.g.add_proposal("p1", "kim@example.com", at(2026, 10, 20, 10), first="Kim")
        f = self.make()
        f.scan()
        self.assertEqual(f.st["customers"]["kim@example.com"]["status"], "no_appointment")

    def test_other_your_proposal_subjects_do_not_count(self):
        self.g.estimates.clear()
        self.g.add_proposal("p1", "pat.testerson@example.com", at(2026, 10, 20, 10),
                            subject="Re: your proposal from the roofer")
        f = self.make()
        self.assertEqual(f.scan()["estimates"], 0)

    def test_read_proposal_keeps_names_never_prices(self):
        hello, names = zf.read_proposal("Hi Pat,\n\nlink\n\nGood: $4,250 total\nBetter Plus: $99/mo with X, or "
                                        "$5,100 total\n$3,000 deal: $3,000 total\n\nPricing is held until Nov 30.")
        self.assertEqual(hello, "Pat")
        self.assertEqual(names, ["Good", "Better Plus"])

    def test_estimate_to_the_office_only_does_not_count(self):
        self.g.add_estimate("e2", "insidesalessupport@zingashome.com", at(2026, 10, 20, 12), "X.pdf")
        f = self.make()
        f.scan()
        self.assertEqual(list(f.st["customers"]), ["pat.testerson@example.com"])

    def test_late_appointment_email_is_matched_later(self):
        self.g.appts = []
        f = self.make()
        f.scan()
        self.assertEqual(self.customer(f)["status"], "no_appointment")
        self.assertIn("pat.testerson@example.com", f.make_plan()["notes"]["no_appointment"])
        self.g.appts.append(appt_msg("a1", at(2026, 10, 19, 18), "Pat and Sam Testerson"))
        f.scan()
        self.assertEqual(self.customer(f)["status"], "active")

    def test_sold_stops_them(self):
        for box, msg in ((self.g.payment, {"to": "pat.testerson@example.com", "subject": "Zinga's Payment Link"}),
                         (self.g.contracts, {"to": "payments@zingashome.com", "subject": "Pat Testerson"}),
                         (self.g.completed, {"to": "pat.testerson@example.com", "sender": "", "subject": "x"})):
            with self.subTest(msg=msg["subject"]):
                for other in (self.g.payment, self.g.contracts, self.g.completed):
                    other.clear()
                box.append(msg)
                f = zf.Followups(self.g, None, vault=tempfile.mkdtemp(dir=self.tmp.name), clock=lambda: self.now)
                f.scan()
                c = self.customer(f)
                self.assertEqual((c["status"], c["why"]), ("stopped", "sold"))
                self.assertTrue(all(t["state"] == "skipped" for t in c["touches"].values()))

    def test_catch_up_sends_only_the_newest_missed_touch(self):
        f = self.make()
        f.scan()
        self.now = at(2026, 10, 30, 7, 40)                # 48 hours and 7 days were missed
        plan = f.make_plan()
        self.assertEqual([i["touch"] for i in plan["items"]], ["7 days"])
        self.assertEqual(zf.parse_iso(plan["items"][0]["due_at"]), at(2026, 10, 30, 8, 5))
        self.assertEqual(self.customer(f)["touches"]["48 hours"]["state"], "skipped")
        item = plan["items"][0]
        self.assertEqual((item["phone"], item["email"], item["email_thread_id"]),
                         ("+13175550142", "pat.testerson@example.com", "t11111111"))

    def test_late_catch_up_waits_for_8_am(self):
        f = self.make()
        f.scan()
        self.now = at(2026, 10, 22, 21, 30)
        item = f.make_plan()["items"][0]
        self.assertEqual(zf.parse_iso(item["due_at"]), at(2026, 10, 23, 8))

    def test_friday_list_has_the_weekend(self):
        self.g.appts = [appt_msg("a1", at(2026, 10, 22, 14), "Pat Testerson")]
        self.g.estimates = []
        self.g.add_estimate("e1", "pat.testerson@example.com", at(2026, 10, 22, 20), "PatTestersonEstimate.pdf")
        f = self.make()
        self.now = at(2026, 10, 22, 21)
        f.scan()
        self.now = at(2026, 10, 23, 7, 40)                 # Friday; 48 hours is Saturday 2 PM
        self.assertEqual([i["touch"] for i in f.make_plan()["items"]], ["48 hours"])

    def test_not_live_never_reaches_quo_bridge(self):
        f = self.make()
        self.now = at(2026, 10, 22, 8, 30)
        f.step()
        self.assertTrue(f.st["plan"]["items"])
        self.assertEqual(self.b.submitted, [])
        self.assertEqual(zf.brief_block(self.now, self.tmp.name), "")

    def test_live_day(self):
        f = self.make(live=True)
        self.now = at(2026, 10, 22, 7, 45)
        f.step()                                           # list made, not sent yet
        self.assertEqual(self.b.submitted, [])
        block = zf.brief_block(self.now, self.tmp.name)
        self.assertIn("Follow-ups due today: 1.", block)
        self.assertIn("1. Pat and Sam Testerson · 48 hours", block)
        self.now = at(2026, 10, 22, 8, 2)
        f.step()
        self.assertEqual(len(self.b.submitted), 1)
        f.step()
        self.assertEqual(len(self.b.submitted), 1)         # once a day
        self.assertEqual(self.customer(f)["touches"]["48 hours"]["state"], "submitted")
        self.b.out = [{"draft_id": "f0", "customer_key": "pat.testerson@example.com", "touch": "48 hours",
                       "status": "sent", "sent_at": z(self.now), "email_status": "sent", "edited": True,
                       "val_draft": "Hi Pat, just checking in on the quote.",
                       "final_text": "Hi Pat, any questions on the shades quote?", "phone": "+13175550142"}]
        self.now = at(2026, 10, 22, 18)
        f.step()
        self.assertEqual(self.b.acked, ["f0"])
        import zingas_voice as zv                          # Gerrit's change to the follow-up: Val learns from it
        pair = zv.read_pairs(self.tmp.name)[-1]
        self.assertEqual((pair["id"], pair["kind"], pair["category"], pair["final_text"]),
                         ("f0", "edited", "followup 48 hours", "Hi Pat, any questions on the shades quote?"))
        self.assertEqual(self.customer(f)["touches"]["48 hours"]["state"], "sent")
        self.assertIn("Follow-ups today: 1 sent", zf.brief_block(self.now, self.tmp.name))
        import zingas_customer as zc                       # the sent text is in the customer's timeline
        entry = zc.timeline("unmatched-3175550142", self.tmp.name)[-1]
        self.assertEqual((entry["channel"], entry["refs"]), ("Text out", ["fu-out:f0"]))

    def test_not_approved_comes_back_next_day(self):
        f = self.make(live=True)
        self.now = at(2026, 10, 22, 8, 2)
        f.step()
        self.b.out = [{"draft_id": "f0", "customer_key": "pat.testerson@example.com", "touch": "48 hours",
                       "status": "expired"}]
        self.now = at(2026, 10, 22, 21)
        f.step()
        self.now = at(2026, 10, 23, 8, 2)
        f.step()
        self.assertEqual([i["touch"] for i in self.b.submitted[-1][1]], ["48 hours"])

    def test_reply_pauses_then_val_writes_after_three_quiet_days(self):
        f = self.make(live=True)
        f.scan()
        self.g.inbox.append({"sender": "pat.testerson@example.com", "messageTimestamp": z(at(2026, 10, 21, 9))})
        self.now = at(2026, 10, 21, 10)
        f.reply_check()
        c = self.customer(f)
        self.assertEqual(c["status"], "paused")
        self.assertEqual(self.b.paused[0][1], "pat.testerson@example.com")
        self.now = at(2026, 10, 23, 10)
        f.reply_check()
        self.assertEqual(c["status"], "paused")            # not 3 days yet
        self.now = at(2026, 10, 24, 10)
        f.reply_check()
        self.assertEqual((c["status"], c["mode"]), ("active", "conversation"))
        self.assertEqual(c["touches"]["48 hours"]["state"], "skipped")
        self.reply = '{"action": "write", "text": "Hey Pat! Did the colors work out?", "email_body": "Hi Pat,\\nThanks!"}'
        self.now = at(2026, 10, 26, 7, 40)
        plan = f.make_plan()
        self.assertEqual([i["touch"] for i in plan["items"]], ["after reply 1"])
        self.assertEqual(plan["items"][0]["text"], "Hey Pat! Did the colors work out?")
        self.assertIn("<conversation>", self.written[0])

    def test_val_can_stop_after_a_conversation(self):
        f = self.make()
        f.scan()
        c = self.customer(f)
        f.resume(c, at(2026, 10, 24, 10))
        self.reply = '{"action": "stop", "why": "they chose another company"}'
        self.now = at(2026, 10, 26, 7, 40)
        plan = f.make_plan()
        self.assertEqual(plan["items"], [])
        self.assertEqual((c["status"], c["why"]), ("stopped", "they chose another company"))

    def test_a_reply_on_gerrits_cell_counts_and_val_sees_it(self):
        f = self.make(live=True)
        f.scan()
        cell = {"pat.testerson@example.com": {
            "last_in": z(at(2026, 10, 21, 9)), "last_out": z(at(2026, 10, 21, 9, 5)),
            "thread": [{"at": "2026-10-21 09:00", "from": "customer", "text": "Can the screen go inside the tracks?"},
                       {"at": "2026-10-21 09:05", "from": "Gerrit", "text": "Absolutely!"}]}}
        with open(os.path.join(self.tmp.name, "followups", "cell-texts.json"), "w") as fh:
            json.dump(cell, fh)
        self.now = at(2026, 10, 24, 11)                 # read 3 days late: already quiet long enough
        f.reply_check()
        c = self.customer(f)
        self.assertEqual(c["status"], "paused")
        f.reply_check()
        self.assertEqual((c["status"], c["mode"]), ("active", "conversation"))
        self.reply = '{"action": "write", "text": "Hey Pat! Any other questions?", "email_body": "Hi Pat,\\nThanks!"}'
        plan = f.make_plan()
        self.assertEqual([i["touch"] for i in plan["items"]], ["after reply 1"])
        self.assertIn("inside the tracks", self.written[0])

    # the upcoming list (the Drafts tab on the website)
    def test_upcoming_shows_the_coming_lists_and_changes_nothing(self):
        f = self.make()
        f.scan()
        up = f.upcoming(14)
        self.assertEqual([(i["list_day"], i["touch"]) for i in up["items"]],
                         [("2026-10-21", "48 hours"), ("2026-10-26", "7 days"), ("2026-11-02", "day 14")])
        self.assertTrue(up["items"][0]["text"].startswith("Hey Pat!"))
        self.assertEqual(up["items"][0]["written_by"], "fixed")
        self.assertTrue(all(t["state"] == "planned" for t in self.customer(f)["touches"].values()))
        self.now = at(2026, 10, 21, 7, 40)                 # once the day's list is made, it leaves the upcoming list
        f.make_plan()
        self.assertEqual([i["touch"] for i in f.upcoming(14)["items"]], ["7 days", "day 14"])

    def test_upcoming_missed_touches_collapse_like_the_real_list(self):
        f = self.make()
        f.scan()
        self.now = at(2026, 10, 31, 10)                    # Saturday: 48 hours and 7 days were missed
        up = f.upcoming(14)
        self.assertEqual([(i["list_day"], i["touch"]) for i in up["items"]],
                         [("2026-11-02", "day 14"), ("2026-11-09", "day 21")])

    def test_val_writes_ahead_once_and_the_day_list_posts_the_same_words(self):
        f = self.make()
        f.scan()
        c = self.customer(f)
        f.resume(c, at(2026, 10, 24, 10))
        self.now = at(2026, 10, 24, 11)                    # Saturday
        self.reply = '{"action": "write", "text": "Hey Pat! Did the colors work out?", "email_body": "Hi Pat,\\nThanks!"}'
        first = f.upcoming(14)["items"][0]
        self.assertEqual((first["list_day"], first["touch"], first["written_by"]), ("2026-10-26", "after reply 1", "val"))
        self.assertEqual(first["text"], "Hey Pat! Did the colors work out?")
        self.assertIn("Monday, October 26", self.written[0])
        n = len(self.written)                              # after reply 1, and day 14 (also hers now)
        self.assertEqual(n, 2)
        f.upcoming(14)
        self.assertEqual(len(self.written), n)             # kept, not written again
        self.reply = '{"action": "write", "text": "Something else", "email_body": "Hi Pat,\\nOther"}'
        self.now = at(2026, 10, 26, 7, 40)
        plan = f.make_plan()
        self.assertEqual(plan["items"][0]["text"], "Hey Pat! Did the colors work out?")
        self.assertEqual(len(self.written), n)

    def test_a_new_message_makes_val_write_again(self):
        f = self.make()
        f.scan()
        c = self.customer(f)
        f.resume(c, at(2026, 10, 24, 10))
        self.now = at(2026, 10, 24, 11)
        self.reply = '{"action": "write", "text": "First try", "email_body": "Hi Pat,\\nA"}'
        f.upcoming(14)
        c["last_any"] = zf.iso(at(2026, 10, 24, 12))       # Gerrit emailed them
        self.reply = '{"action": "write", "text": "Second try", "email_body": "Hi Pat,\\nB"}'
        self.assertEqual(f.upcoming(14)["items"][0]["text"], "Second try")
        self.assertEqual(len(self.written), 4)             # both of hers, written again once each

    def test_upcoming_val_stop_is_only_a_note(self):
        f = self.make()
        f.scan()
        c = self.customer(f)
        f.resume(c, at(2026, 10, 24, 10))
        self.reply = '{"action": "stop", "why": "they chose another company"}'
        item = f.upcoming(14)["items"][0]
        self.assertEqual((item["text"], item["note"]), ("", "Val would close this one: they chose another company"))
        self.assertEqual(c["status"], "active")

    def test_upcoming_names_who_is_on_hold(self):
        f = self.make(live=True)
        f.scan()
        self.g.inbox.append({"sender": "pat.testerson@example.com", "messageTimestamp": z(at(2026, 10, 21, 9))})
        self.now = at(2026, 10, 21, 10)
        f.reply_check()
        up = f.upcoming(14)
        self.assertEqual(up["items"], [])
        self.assertEqual(up["held"], [{"customer_name": "Pat and Sam Testerson", "why": "they wrote back",
                                       "back_on": "2026-10-24"}])

    def test_step_sends_the_upcoming_list_every_15_minutes(self):
        sent = []

        class Site:
            fail = False

            def post(self, path, body):
                if Site.fail:
                    raise RuntimeError("website /api/assistant/upcoming: HTTP 503")
                sent.append((path, body))
                return {"ok": True}

        f = zf.Followups(self.g, self.b, vault=self.tmp.name, clock=lambda: self.now, site=Site())
        f.step()
        self.assertEqual([p for p, _ in sent], ["/api/assistant/upcoming"])
        self.assertEqual(sent[0][1]["items"][0]["touch"], "48 hours")
        f.step()
        self.assertEqual(len(sent), 1)
        self.now += timedelta(minutes=16)
        Site.fail = True
        f.step()                                           # the website down never stops follow-ups
        self.assertEqual(len(sent), 1)
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "followups", "state.json")))

    def test_no_cell_file_changes_nothing(self):
        f = self.make(live=True)
        f.scan()
        self.now = at(2026, 10, 21, 10)
        f.reply_check()
        self.assertEqual(self.customer(f)["status"], "active")

    def test_texts_count_as_a_reply_and_dnc_stops(self):
        f = self.make(live=True)
        f.scan()
        self.b.texts["+13175550142"] = {"last_in": z(at(2026, 10, 21, 9)), "last_out": None, "dnc": False}
        self.now = at(2026, 10, 21, 10)
        f.reply_check()
        self.assertEqual(self.customer(f)["status"], "paused")
        self.b.texts["+13175550142"]["dnc"] = True
        f.reply_check()
        self.assertEqual(self.customer(f)["why"], "do not contact")

    def test_state_has_tight_permissions(self):
        f = self.make()
        f.scan()
        f.save()
        mode = os.stat(os.path.join(self.tmp.name, "followups", "state.json")).st_mode & 0o777
        self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
