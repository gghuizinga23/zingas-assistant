"""Tests for F0 quote follow-ups in quo-bridge, with fake Quo, Telegram and Gmail.
Every call goes through the real WSGI app, so the locks are tested too."""

import unittest
from datetime import timedelta, timezone

from clients import EmailError
from followups import followup_id
from test_bridge import CRON, CUSTOMER, GERRIT_CELL, Rig, TUE_11AM, TUE_9PM

DAY = "2026-10-20"
OTHER = "+13175550177"


class FakeEmail:
    def __init__(self, known=("pat@example.com", "sam@example.com"), fail=False):
        self.known, self.fail, self.sent = set(known), fail, []

    def got_estimate(self, email):
        return email in self.known

    def send(self, to, subject, body, thread_id=""):
        if self.fail:
            raise EmailError("Composio GMAIL_REPLY_TO_THREAD: HTTP 500")
        self.sent.append({"to": to, "subject": subject, "body": body, "thread": thread_id})
        return "m1"


def item(key="pat@example.com", touch="48 hours", phone=CUSTOMER, due=None, **extra):
    row = {"customer_key": key, "customer_name": "Pat Lee", "touch": touch, "phone": phone,
           "email": key if "@" in key else "", "text": "Hey Pat! Just checking in on the shades estimate.",
           "email_subject": "Following up", "email_body": "Hi Pat,\n\nJust following up.\n\nThanks!\nGerrit",
           "email_thread_id": "18f00aa", "time_zone": "America/Indiana/Indianapolis",
           "due_at": (due or TUE_11AM + timedelta(hours=2)).isoformat()}
    row.update(extra)
    return row


class Base(unittest.TestCase):
    def rig(self, now=TUE_11AM, email=True):
        r = Rig(now=now)
        r.bridge.email = FakeEmail() if email else None
        return r

    def submit(self, r, items, day=DAY):
        return r.val("POST", "/api/val/followups", {"day": day, "items": items})

    def batch_card(self, r):
        return [m for m in r.tg.sent if m["text"].startswith("🪟 Follow-ups")][-1]


class Listing(Base):
    def test_list_makes_one_card_and_a_second_send_changes_nothing(self):
        r = self.rig()
        st, out = self.submit(r, [item(), item("sam@example.com", "7 days", OTHER, customer_name="Sam Ray")])
        self.assertEqual(st, 200)
        self.assertEqual([i["status"] for i in out["items"]], ["planned", "planned"])
        card = self.batch_card(r)
        self.assertIn("Pat Lee · 48 hours", card["text"])
        self.assertEqual([b[0]["callback_data"] for b in card["buttons"]], ["fa:" + DAY, "fr:" + DAY])
        st, out = self.submit(r, [item()])
        self.assertEqual(out["items"][0]["status"], "already_listed")
        self.assertEqual(len([m for m in r.tg.sent if m["text"].startswith("🪟")]), 1)   # edited, not re-sent
        self.assertEqual(r.quo.sent, [])

    def test_locks(self):
        r = self.rig()
        self.assertEqual(r.val("POST", "/api/val/followups", {"day": DAY, "items": [item()]}, token="nope")[0], 401)
        self.assertEqual(r.call("POST", "/api/val/followups", {"day": DAY, "items": [item()]},
                                {"Authorization": "Bearer " + CRON})[0], 401)
        self.assertEqual(r.val("GET", "/api/val/followups/outcomes", token="")[0], 401)
        # Val's code can't press Approve all: taps come only from Telegram with its secret
        self.submit(r, [item(due=TUE_11AM - timedelta(minutes=1))])
        self.assertEqual(r.call("POST", "/api/telegram", {"callback_query": {"from": {"id": 111}, "data": "fa:" + DAY}},
                                {"Authorization": "Bearer val-token-abc"})[0], 401)
        r.tap("fa", DAY, who=999)           # not Gerrit
        self.assertEqual(r.quo.sent, [])

    def test_bad_items_refused(self):
        r = self.rig()
        for bad in (item(email="not-an-email"), item(phone="12"), item(touch="x" * 40),
                    item(text="", email="", email_body=""), item(email_subject="a\nBcc: x@y.com"),
                    item(due_at=""), item(email_thread_id="../../x")):
            st, _ = self.submit(r, [bad])
            self.assertEqual(st, 400, bad)
        self.assertEqual(self.submit(r, [item(touch=f"day {n}") for n in range(41)])[0], 400)

    def test_do_not_contact_is_blocked_at_listing(self):
        r = self.rig()
        r.customer_texts("STOP")
        st, out = self.submit(r, [item()])
        self.assertEqual(out["items"][0]["status"], "blocked")
        r.tap("fa", DAY)
        r.clock.t += timedelta(hours=3)
        r.tick()
        self.assertEqual([t for t in r.quo.sent if t[0] == CUSTOMER], [])


class ApproveAll(Base):
    def test_approve_all_waits_for_each_time_then_sends_text_and_email(self):
        r = self.rig()
        self.submit(r, [item(), item("sam@example.com", "7 days", OTHER, due=TUE_11AM - timedelta(minutes=5),
                                      customer_name="Sam Ray")])
        r.tap("fa", DAY)
        sam, pat = followup_id("sam@example.com", "7 days", DAY), followup_id("pat@example.com", "48 hours", DAY)
        self.assertEqual(r.status(sam), "sent")          # already due: went at once
        self.assertEqual(r.status(pat), "held")
        self.assertEqual(r.quo.sent, [(OTHER, item()["text"])])
        r.clock.t += timedelta(hours=2)
        r.tick()
        self.assertEqual(r.status(pat), "sent")
        self.assertEqual(r.quo.sent[-1], (CUSTOMER, item()["text"]))
        self.assertEqual([e["to"] for e in r.bridge.email.sent], ["sam@example.com", "pat@example.com"])
        self.assertEqual(r.bridge.email.sent[-1]["thread"], "18f00aa")
        self.assertIn("✅ Pat Lee", r.tg.edits[-1]["text"])
        out = r.val("GET", "/api/val/followups/outcomes")[1]["outcomes"]
        self.assertEqual({o["touch"]: (o["status"], o["email_status"]) for o in out},
                         {"48 hours": ("sent", "sent"), "7 days": ("sent", "sent")})
        # Val's normal pickup never sees follow-up outcomes
        self.assertEqual(r.val("GET", "/api/val/updates")[1]["outcomes"], [])

    def test_customer_who_texted_since_the_list_is_paused(self):
        r = self.rig()
        self.submit(r, [item()])
        r.tap("fa", DAY)
        r.clock.t += timedelta(minutes=30)
        r.customer_texts("Can you come back Thursday?")
        r.clock.t += timedelta(hours=2)
        r.tick()
        pid = followup_id("pat@example.com", "48 hours", DAY)
        self.assertEqual(r.status(pid), "paused")
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.bridge.email.sent, [])

    def test_not_approved_by_8pm_nothing_sends(self):
        r = self.rig()
        self.submit(r, [item()])
        r.clock.t = TUE_9PM
        self.assertEqual(r.tick()[1]["followups_expired"], 1)
        self.assertEqual(r.status(followup_id("pat@example.com", "48 hours", DAY)), "expired")
        self.assertEqual(r.quo.sent, [])
        r.tap("fa", DAY)                                  # too late now
        self.assertEqual(r.quo.sent, [])

    def test_approved_but_after_8pm_their_time_waits_for_the_next_list(self):
        r = self.rig()
        self.submit(r, [item(due=TUE_11AM + timedelta(hours=10))])     # 7 pm: approve now, late tick
        r.tap("fa", DAY)
        r.clock.t = TUE_9PM
        r.tick()
        self.assertEqual(r.status(followup_id("pat@example.com", "48 hours", DAY)), "expired")
        self.assertEqual(r.quo.sent, [])

    def test_follow_up_cards_never_text_gerrits_cell(self):
        r = self.rig()
        self.submit(r, [item()])
        r.tap("fr", DAY)
        r.clock.t += timedelta(minutes=30)
        r.tick()
        self.assertNotIn(GERRIT_CELL, [t[0] for t in r.quo.sent])


class Email(Base):
    def test_email_to_someone_who_never_got_an_estimate_is_refused(self):
        r = self.rig()
        self.submit(r, [item("eve@example.com", due=TUE_11AM - timedelta(minutes=1))])
        r.tap("fa", DAY)
        d = r.store.get_draft(followup_id("eve@example.com", "48 hours", DAY))
        self.assertEqual((d["status"], d["email_status"]), ("sent", "refused"))   # the text still went
        self.assertEqual(r.bridge.email.sent, [])

    def test_email_not_set_up_yet_still_sends_the_text(self):
        r = self.rig(email=False)
        self.submit(r, [item(due=TUE_11AM - timedelta(minutes=1))])
        r.tap("fa", DAY)
        d = r.store.get_draft(followup_id("pat@example.com", "48 hours", DAY))
        self.assertEqual((d["status"], d["email_status"]), ("sent", "not_set_up"))
        self.assertEqual(len(r.quo.sent), 1)

    def test_email_only_customer(self):
        r = self.rig()
        self.submit(r, [item(phone="", due=TUE_11AM - timedelta(minutes=1))])
        r.tap("fa", DAY)
        d = r.store.get_draft(followup_id("pat@example.com", "48 hours", DAY))
        self.assertEqual((d["status"], d["email_status"]), ("sent", "sent"))
        self.assertEqual(r.quo.sent, [])

    def test_email_only_and_email_fails_can_be_tried_again(self):
        r = self.rig()
        r.bridge.email.fail = True
        self.submit(r, [item(phone="", due=TUE_11AM - timedelta(minutes=1))])
        r.tap("fa", DAY)
        pid = followup_id("pat@example.com", "48 hours", DAY)
        self.assertEqual(r.status(pid), "failed")
        r.bridge.email.fail = False
        r.tap("a", pid)
        self.assertEqual(r.status(pid), "sent")
        self.assertEqual(len(r.bridge.email.sent), 1)

    def test_text_is_never_sent_twice_when_the_email_is_retried(self):
        r = self.rig()
        self.submit(r, [item(due=TUE_11AM - timedelta(minutes=1))])
        r.tap("fa", DAY)
        self.assertEqual(len(r.quo.sent), 1)
        r.tap("a", followup_id("pat@example.com", "48 hours", DAY))      # nothing left to do
        self.assertEqual(len(r.quo.sent), 1)


class Review(Base):
    def test_review_one_by_one(self):
        r = self.rig()
        self.submit(r, [item(), item("sam@example.com", "7 days", OTHER, customer_name="Sam Ray"),
                        item("pat@example.com", "day 14", due=TUE_11AM + timedelta(hours=3))])
        r.tap("fr", DAY)
        cards = [m for m in r.tg.sent if m["text"].startswith("🔁")]
        self.assertEqual(len(cards), 3)
        pat48, sam7, pat14 = (followup_id("pat@example.com", "48 hours", DAY), followup_id("sam@example.com", "7 days", DAY),
                              followup_id("pat@example.com", "day 14", DAY))
        r.tap("a", sam7)
        self.assertEqual(r.status(sam7), "held")             # its time is later today
        r.tap("q", pat48)                                     # no more follow-ups for Pat
        self.assertEqual((r.status(pat48), r.status(pat14)), ("stopped_customer", "stopped_customer"))
        r.clock.t += timedelta(hours=4)
        r.tick()
        self.assertEqual(r.status(sam7), "sent")
        self.assertEqual([t[0] for t in r.quo.sent], [OTHER])

    def test_edit_text_then_approve(self):
        r = self.rig()
        self.submit(r, [item(due=TUE_11AM - timedelta(minutes=1))])
        r.tap("fr", DAY)
        pid = followup_id("pat@example.com", "48 hours", DAY)
        r.tap("e", pid)
        prompt = r.tg.sent[-1]["id"]
        r.reply("Hey Pat! Any questions on the shades?", to_message_id=prompt)
        r.tap("a", pid)
        self.assertEqual(r.quo.sent, [(CUSTOMER, "Hey Pat! Any questions on the shades?")])
        out = r.val("GET", "/api/val/followups/outcomes")[1]["outcomes"][0]
        self.assertTrue(out["edited"])

    def test_remove_one(self):
        r = self.rig()
        self.submit(r, [item()])
        r.tap("fr", DAY)
        r.tap("s", followup_id("pat@example.com", "48 hours", DAY))
        self.assertEqual(r.status(followup_id("pat@example.com", "48 hours", DAY)), "skipped")


class ValDoors(Base):
    def test_pause_by_email_or_phone(self):
        r = self.rig()
        self.submit(r, [item(), item("sam@example.com", "7 days", OTHER, customer_name="Sam Ray")])
        r.tap("fa", DAY)
        self.assertEqual(r.val("POST", "/api/val/followups/pause", {"email": "PAT@example.com"})[1], {"paused": 1})
        self.assertEqual(r.val("POST", "/api/val/followups/pause", {"phone": OTHER})[1], {"paused": 1})
        self.assertEqual(r.val("POST", "/api/val/followups/pause", {})[0], 400)
        r.clock.t += timedelta(hours=3)
        r.tick()
        self.assertEqual(r.quo.sent, [])

    def test_contacts(self):
        r = self.rig()
        r.customer_texts("Thanks!")
        r.customer_texts("STOP", phone=OTHER)
        st, out = r.val("POST", "/api/val/followups/contacts", {"phones": [CUSTOMER, OTHER, "junk"],
                                                                 "thread_for": [CUSTOMER]})
        c = out["contacts"]
        self.assertEqual(set(c), {CUSTOMER, OTHER})
        self.assertTrue(c[CUSTOMER]["last_in"])
        self.assertFalse(c[CUSTOMER]["dnc"])
        self.assertTrue(c[OTHER]["dnc"])
        self.assertEqual(c[CUSTOMER]["thread"][0]["text"], "Thanks!")
        self.assertEqual(c[OTHER]["thread"], [])


if __name__ == "__main__":
    unittest.main()
