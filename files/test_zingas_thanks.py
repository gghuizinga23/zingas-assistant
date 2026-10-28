"""Tests for zingas_thanks.py. Every name, email and phone here is made up.
Run: python3 -m unittest files/test_zingas_thanks.py"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quo-bridge"))

import send_gate  # noqa: E402
import zingas_customer as zc  # noqa: E402
import zingas_thanks as th  # noqa: E402

TZ = th.TZ
GOOD = ("Hey Pat! This is Gerrit Huizinga with Zinga's!\n\nThanks again for having me out today! It was great "
        "meeting you, and congrats again on the new puppy!\n\nI just finished putting together your quotes for both "
        "the track screens and the cable-guided screens and emailed them over to you. If you and Sam would like me "
        "to stop back out to go over screen colors, I'd be more than happy to!\n\nHope the soccer game goes well "
        "today haha!\n\nThanks!\nGerrit")


def at(d, h=0, mi=0):
    return datetime(2026, 10, d, h, mi, tzinfo=TZ)


def z(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeBridge:
    def __init__(self, fail=None):
        self.drafts, self.fail = [], fail
        self.asks, self.closed = {}, {}

    def call(self, method, path, body):
        assert (method, path) == ("POST", "/api/val/asks")
        if body["op"] == "open":
            i = "q" + str(len(self.asks) + 1)
            self.asks[i] = {"to": body["to"], "name": body["customer_name"], "status": "asking"}
            return {"id": i, "status": "asking"}
        if body["op"] == "status":
            return {"asks": {i: self.asks[i]["status"] for i in body["ids"] if i in self.asks}}
        self.asks[body["id"]]["status"] = "closed"
        self.closed[body["id"]] = body["note"]
        return {"id": body["id"], "status": "closed"}

    def draft(self, payload):
        if self.fail:
            raise self.fail
        self.drafts.append(payload)
        return {"id": "d" + str(len(self.drafts)), "status": "pending"}


class Refused(RuntimeError):
    status = 409


class ThanksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = self.tmp.name
        self.now = at(27, 15)
        self.answers, self.prompts = [], []
        self.bridge = FakeBridge()
        self.customers = {}
        self.add_customer()
        # the first run marks "since": start every test as if it was installed in the morning
        with th.locked(self.vault) as st:
            st["since"] = th.iso(at(27, 6))

    def tearDown(self):
        self.tmp.cleanup()

    # helpers -----------------------------------------------------------
    def add_customer(self, email="pat.testerson@example.com", name="Testerson, Pat", phone="+13175550142",
                     appt=None, sent=None, quoted=("Track screens", "Cable-guided screens"), status="active", **kw):
        c = {"email": email, "name": name, "first": "", "phone": phone, "time_zone": "America/Indiana/Indianapolis",
             "appt_at": z(appt or at(27, 12)), "est_sent_at": z(sent or at(27, 14, 30)), "est_thread": "t1",
             "est_msg": "m1", "status": status, "quoted": list(quoted), "product": "screens", "est_kind": "proposal"}
        c.update(kw)
        self.customers[email] = c
        os.makedirs(os.path.join(self.vault, "followups"), exist_ok=True)
        with open(os.path.join(self.vault, "followups", "state.json"), "w") as fh:
            json.dump({"customers": self.customers}, fh)
        return c

    def add_visit(self, pid="P-100", phone="+13175550142", day="2026-10-27",
                  summary="New puppy named Biscuit. Wife Sam wants to pick screen colors. Soccer game tonight."):
        zc.ensure_profile(pid, self.vault, name="Pat Testerson", phone=phone)
        folder = zc.paths(pid, self.vault)["visits"]
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, f"{day}-abc123.md"), "w") as fh:
            fh.write(f"# Visit {day}\n\n{summary}\n\n## Transcript\nGerrit: hello there\n")

    def ask(self, prompt):
        self.prompts.append(prompt)
        return self.answers.pop(0) if self.answers else json.dumps({"text": GOOD})

    def make(self, bridge="default"):
        return th.Thanks(self.bridge if bridge == "default" else bridge, vault=self.vault, ask_val=self.ask,
                         clock=lambda: self.now)

    # the thank-you -----------------------------------------------------
    def test_recording_then_estimate_makes_one_thank_you(self):
        self.add_visit()
        t = self.make()
        self.assertEqual(t.once()["thanked"], 1)
        self.assertEqual(len(self.bridge.drafts), 1)
        d = self.bridge.drafts[0]
        self.assertEqual(d["category"], "thank_you")
        self.assertEqual(d["to"], "+13175550142")
        self.assertEqual(d["customer_name"], "Pat")
        self.assertEqual(d["prospect_id"], "P-100")
        self.assertEqual(d["text"], GOOD)
        self.assertIn("Biscuit", self.prompts[0])               # the visit reached Val
        self.assertNotIn("hello there", self.prompts[0])        # the transcript itself did not
        self.assertIn("Track screens and Cable-guided screens", self.prompts[0])
        self.assertNotIn("$", self.prompts[0])
        self.now += timedelta(minutes=2)
        self.assertEqual(t.once()["thanked"], 0)                 # once only
        self.assertEqual(len(self.bridge.drafts), 1)

    def test_estimate_first_waits_for_the_recording(self):
        t = self.make()
        n = t.once()
        self.assertEqual((n["thanked"], n["waiting"]), (0, 1))
        self.assertEqual(self.prompts, [])
        self.now = at(27, 15, 45)
        self.add_visit()
        self.assertEqual(t.once()["thanked"], 1)
        self.assertIn("Biscuit", self.prompts[0])

    def test_no_recording_after_two_hours_writes_from_the_estimate(self):
        self.now = at(27, 16, 31)
        self.assertEqual(self.make().once()["thanked"], 1)
        self.assertIn("no recording of this visit yet", self.prompts[0])
        st = th.read_state(self.vault)
        self.assertIn("no recording", list(st["done"].values())[0]["what"])

    def test_a_recording_of_another_day_is_not_this_visit(self):
        self.add_visit(day="2026-10-01")
        self.assertEqual(self.make().once()["waiting"], 1)

    def test_revised_estimate_gets_no_second_thank_you(self):
        self.add_visit()
        t = self.make()
        t.once()
        self.add_customer(est_thread="t2", est_msg="m2")         # F0 keeps the first send time, new thread
        self.now += timedelta(minutes=30)
        t.once()
        self.assertEqual(len(self.bridge.drafts), 1)

    def test_estimate_before_the_listed_time_on_the_visit_day(self):
        # Gina Willis, Oct 28: Salesforce said 5 PM, the estimate went out at 3:57 PM.
        self.customers.clear()
        self.add_customer(appt=at(27, 17), sent=at(27, 15, 57))
        self.add_visit()
        self.now = at(27, 16)
        self.assertEqual(self.make().once()["thanked"], 1)

    def test_the_estimate_email_is_the_trigger_whatever_the_listed_visit(self):
        # Gerrit (Oct 28): visits get moved up, back or around; the estimate going out is what counts.
        self.customers.clear()
        self.add_customer(appt=at(28, 10), sent=at(27, 15))      # still listed for tomorrow
        self.add_visit()                                          # recorded today
        self.now = at(27, 15, 2)
        self.assertEqual(self.make().once()["thanked"], 1)
        self.assertIn("say 'today'", self.prompts[0])

    def test_recording_days_follow_the_estimate_email(self):
        c = {"est_sent_at": z(at(27, 15)), "appt_at": z(at(30, 10))}
        self.assertEqual(th.visit_days(c)[:5], ["2026-10-24", "2026-10-25", "2026-10-26", "2026-10-27", "2026-10-29"])

    def test_wording_day_without_a_recording(self):
        late = {"est_sent_at": z(at(27, 15)), "appt_at": z(at(23, 10)), "quoted": []}
        self.assertIn("say 'on Friday'", th.write_prompt(late, "", "", at(27, 15)))
        moved_up = {"est_sent_at": z(at(27, 15)), "appt_at": z(at(28, 10)), "quoted": []}
        self.assertIn("say 'today'", th.write_prompt(moved_up, "", "", at(27, 15)))

    # Gerrit's "no recording yet" card ------------------------------------
    def test_no_recording_puts_up_the_question_at_once(self):
        t = self.make()
        self.assertEqual(t.once()["waiting"], 1)
        self.assertEqual(list(self.bridge.asks.values()), [{"to": "+13175550142", "name": "Pat", "status": "asking"}])
        self.now += timedelta(minutes=2)
        t.once()
        self.assertEqual(len(self.bridge.asks), 1)                # one card per estimate
        self.assertEqual(self.bridge.drafts, [])

    def test_draft_now_writes_it_without_the_recording(self):
        t = self.make()
        t.once()
        self.bridge.asks["q1"]["status"] = "draft_now"            # Gerrit tapped Draft now
        self.now += timedelta(minutes=2)
        self.assertEqual(t.once()["thanked"], 1)
        self.assertIn("no recording of this visit yet", self.prompts[0])
        self.assertIn("Gerrit: draft now", list(th.read_state(self.vault)["done"].values())[0]["what"])
        self.assertIn("no recording", self.bridge.closed["q1"])
        self.assertEqual(th.read_state(self.vault)["asks"], {})

    def test_wait_then_the_recording_comes_in(self):
        t = self.make()
        t.once()
        self.bridge.asks["q1"]["status"] = "waiting_recording"
        self.now += timedelta(minutes=30)
        self.assertEqual(t.once()["waiting"], 1)
        self.add_visit()
        self.now += timedelta(minutes=2)
        self.assertEqual(t.once()["thanked"], 1)
        self.assertIn("Biscuit", self.prompts[0])
        self.assertIn("recording came in", self.bridge.closed["q1"])

    def test_no_tap_still_drafts_after_two_hours(self):
        t = self.make()
        t.once()
        self.now = at(27, 16, 31)
        self.assertEqual(t.once()["thanked"], 1)
        self.assertIn("q1", self.bridge.closed)

    def test_a_recording_already_in_needs_no_question(self):
        self.add_visit()
        self.make().once()
        self.assertEqual(self.bridge.asks, {})

    def test_old_quo_bridge_without_questions_still_waits(self):
        class Old(FakeBridge):
            call = None
        b = Old()
        t = self.make(b)
        self.assertEqual(t.once()["waiting"], 1)
        self.now = at(27, 16, 31)
        self.assertEqual(t.once()["thanked"], 1)

    def test_old_estimates_no_phone_or_sold_are_left_alone(self):
        self.add_customer(email="old@example.com", phone="+13175550101", sent=at(27, 5))    # before install
        self.add_customer(email="late@example.com", phone="+13175550102", appt=at(20, 12), sent=at(26, 9))  # a day old
        self.add_customer(email="nophone@example.com", phone="", sent=at(27, 9))
        self.add_customer(email="sold@example.com", phone="+13175550103", status="sold", sent=at(27, 9))
        self.now = at(27, 18)
        self.make().once()
        self.assertEqual([d["to"] for d in self.bridge.drafts], ["+13175550142"])

    def test_money_or_missing_email_is_refused_then_fallback(self):
        self.answers = [json.dumps({"text": GOOD.replace("emailed them", "emailed them ($4,250)")}),
                        json.dumps({"text": GOOD.replace("emailed them over to you", "sent them over")})]
        self.add_visit()
        t = self.make()
        self.assertEqual(t.once()["thanked"], 0)                 # first bad answer: try again next look
        self.assertEqual(t.once()["thanked"], 1)                 # second: the plain fallback
        text = self.bridge.drafts[0]["text"]
        self.assertTrue(text.startswith("Hey Pat! This is Gerrit Huizinga with Zinga's!"))
        self.assertIn("quotes for Track screens and Cable-guided screens and emailed them over", text)
        self.assertTrue(text.endswith("Thanks!\nGerrit"))
        self.assertEqual(send_gate.money_terms(text), [])

    def test_check_text_rules(self):
        self.assertEqual(th.check_text(GOOD, "Pat"), GOOD)
        self.assertIsNone(th.check_text(GOOD, "Kim"))                                  # wrong name
        self.assertIsNone(th.check_text(GOOD.replace("Thanks!\nGerrit", "Gerrit"), "Pat"))
        self.assertIsNone(th.check_text(GOOD + " " + "x" * 600, "Pat"))
        self.assertIsNone(th.check_text(GOOD.replace("today haha", "today, 20% off haha"), "Pat"))
        self.assertIn(", ", th.check_text(GOOD.replace("today haha", "today — haha"), "Pat"))
        self.assertEqual(send_gate.money_terms(GOOD), [])

    def test_the_name_they_go_by(self):
        mike = GOOD.replace("Hey Pat!", "Hey Mike!")
        self.assertIsNone(th.check_text(mike, "Michael"))
        self.assertEqual(th.check_text(mike, "Michael", "talk: goes by Mike, short texts"), mike)
        self.assertIsNone(th.check_text(mike, "Michael", "Mikey called"))
        self.assertIsNone(th.check_text(GOOD.replace("Hey Pat!", "Hey there!"), "Pat", "there"))

    def test_names(self):
        self.assertEqual(th.first_name("Testerson, Pat"), "Pat")
        self.assertEqual(th.first_name("Dennin, Jeff & Erika"), "Jeff")
        self.assertEqual(th.first_name("pat lee"), "Pat")
        self.assertEqual(th.first_name("pat@example.com"), "")
        self.assertEqual(th.quoted_words({"quoted": ["A"], "product": "x"}), "A")
        self.assertEqual(th.quoted_words({"quoted": ["$5,000 deal"], "product": "blinds and shades"}),
                         "blinds and shades")

    def test_do_not_contact_is_not_tried_again(self):
        self.add_visit()
        t = self.make(bridge=FakeBridge(fail=Refused("do-not-contact")))
        t.once()
        self.now += timedelta(minutes=2)
        t.once()
        self.assertEqual(len(self.prompts), 1)

    def test_bridge_down_tries_again(self):
        self.add_visit()
        self.make(bridge=FakeBridge(fail=RuntimeError("down"))).once()
        self.make().once()
        self.assertEqual(len(self.bridge.drafts), 1)

    # Plaud's own draft --------------------------------------------------
    def test_plaud_draft_is_replaced_by_the_thank_you(self):
        self.add_visit()
        self.assertTrue(th.hold_plaud_drafts(["Great to meet you Pat!"], "+13175550142", "Pat", "P-100",
                                             "America/Indiana/Indianapolis", "f1", vault=self.vault, now=at(27, 13)))
        t = self.make()
        n = t.once()
        self.assertEqual((n["thanked"], n["plaud_dropped"]), (1, 1))
        self.now = at(27, 20)
        t.once()
        self.assertEqual([d["category"] for d in self.bridge.drafts], ["thank_you"])

    def test_plaud_draft_held_after_the_thank_you_is_dropped(self):
        self.now = at(27, 16, 31)
        t = self.make()
        t.once()                                                  # estimate-only thank-you
        th.hold_plaud_drafts(["Great to meet you Pat!"], "+13175550142", "Pat", "P-100",
                             "America/Indiana/Indianapolis", "f1", vault=self.vault, now=self.now)
        self.now = at(27, 19)
        self.assertEqual(t.once()["plaud_dropped"], 1)
        self.assertEqual(len(self.bridge.drafts), 1)

    def test_plaud_draft_goes_out_when_no_estimate_comes(self):
        self.customers.clear()
        self.add_customer(email="other@example.com", phone="+13175550199", sent=at(26, 10), appt=at(26, 9))
        th.hold_plaud_drafts(["Great to meet you Pat!", "Here is the care guide I promised."], "+13175550142",
                             "Pat", "P-100", "America/Indiana/Indianapolis", "f1", vault=self.vault, now=at(27, 13))
        t = self.make()
        self.now = at(27, 14, 59)
        self.assertEqual(t.once()["plaud_sent"], 0)              # still inside the 2 hours
        self.now = at(27, 15, 1)
        self.assertEqual(t.once()["plaud_sent"], 1)
        self.assertEqual([d["text"] for d in self.bridge.drafts],
                         ["Great to meet you Pat!", "Here is the care guide I promised."])
        self.assertEqual({d["category"] for d in self.bridge.drafts}, {"reply"})
        # an estimate email that shows up later never adds a second thank-you
        self.add_customer(sent=at(27, 16), appt=at(27, 12))
        self.now = at(27, 18, 30)
        t.once()
        self.assertEqual(len(self.bridge.drafts), 2)
        self.assertIn("Plaud", json.dumps(th.read_state(self.vault)["done"]))

    def test_nothing_to_hold(self):
        self.assertFalse(th.hold_plaud_drafts([], "+13175550142", "Pat", "P", "UTC", "f", vault=self.vault))
        self.assertFalse(th.hold_plaud_drafts(["hi"], "", "Pat", "P", "UTC", "f", vault=self.vault))

    def test_state_has_tight_permissions(self):
        self.make().once()
        mode = os.stat(th.paths(self.vault)["state"]).st_mode & 0o777
        self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
