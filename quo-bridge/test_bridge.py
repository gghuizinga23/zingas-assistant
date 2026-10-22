"""End-to-end tests for quo-bridge with fake texts. Nothing here reaches Quo,
Telegram or Supabase: they're swapped for fakes, and the clock is fixed.

Each test goes through the real WSGI app where a lock is involved, so the
locks themselves are tested too."""

import base64
import io
import json
import unittest
from datetime import datetime, timedelta, timezone

import app as wsgi
from bridge import Bridge, Config
from clients import QuoError, sign_quo_body
from store import MemoryStore

QUO_SECRET = "whsec_" + base64.b64encode(b"q" * 24).decode()
TG_SECRET = "tg-secret-123"
VAL_TOKEN = "val-token-abc"
CRON = "cron-secret-xyz"
GERRIT_TG = 111
CUSTOMER = "+13175550123"
GERRIT_CELL = "+13175550999"

TUE_11AM = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)    # 11:00 am in Indianapolis
TUE_9PM = datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc)      # 9:00 pm in Indianapolis


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class FakeQuo:
    def __init__(self):
        self.sent = []
        self.fail_with = []

    def send_text(self, to, text):
        if self.fail_with:
            raise self.fail_with.pop(0)
        self.sent.append((to, text))
        return f"AC{len(self.sent):04d}"


class FakeTelegram:
    def __init__(self):
        self.sent, self.edits, self.answers = [], [], []

    def send(self, chat_id, text, buttons=None, force_reply=False):
        self.sent.append({"chat": chat_id, "text": text, "buttons": buttons, "force_reply": force_reply,
                          "id": 500 + len(self.sent)})
        return self.sent[-1]["id"]

    def edit(self, chat_id, message_id, text, buttons=None):
        self.edits.append({"id": message_id, "text": text, "buttons": buttons})

    def answer(self, callback_id, text=""):
        self.answers.append(text)

    def last_card(self):
        return [m for m in self.sent if m["buttons"]][-1]


class Rig:
    def __init__(self, now=TUE_11AM, auto_send=False, gerrit_cell=GERRIT_CELL):
        self.clock = Clock(now)
        self.store, self.quo, self.tg = MemoryStore(), FakeQuo(), FakeTelegram()
        cfg = Config(quo_webhook_secret=QUO_SECRET, telegram_webhook_secret=TG_SECRET, approver_id=GERRIT_TG,
                     val_token=VAL_TOKEN, cron_secret=CRON, gerrit_cell=gerrit_cell, auto_send_enabled=auto_send)
        self.bridge = Bridge(cfg, self.store, self.quo, self.tg, now=self.clock)
        self.app = wsgi.make_app(lambda: self.bridge)
        self._n = 0

    def call(self, method, path, body=b"", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "CONTENT_LENGTH": str(len(body)),
                   "wsgi.input": io.BytesIO(body)}
        for k, v in (headers or {}).items():
            environ["HTTP_" + k.upper().replace("-", "_")] = v
        got = {}
        raw = b"".join(self.app(environ, lambda status, h: got.setdefault("status", status)))
        return int(got["status"].split()[0]), json.loads(raw)

    # the four kinds of caller
    def customer_texts(self, text, phone=CUSTOMER, msg_id=None, secret=QUO_SECRET):
        self._n += 1
        msg_id = msg_id or f"ACin{self._n}"
        raw = json.dumps({"id": "EV" + msg_id, "type": "message.received", "data": {
            "resource": {"id": msg_id, "direction": "incoming", "text": text, "createdAt":
                         (self.clock() - timedelta(seconds=1)).isoformat()},
            "context": {"phoneNumberId": "PNbiz", "senderIdentifier": phone}}}).encode()
        ts = int(self.clock().timestamp())
        sig = sign_quo_body(raw, secret, "EV" + msg_id, ts)
        return self.call("POST", "/api/quo", raw, {"webhook-id": "EV" + msg_id, "webhook-timestamp": str(ts),
                                                    "webhook-signature": sig})

    def quo_event(self, kind, resource, external=(CUSTOMER,), secret=QUO_SECRET):
        self._n += 1
        ev = f"EVcall{self._n}"
        raw = json.dumps({"id": ev, "type": kind, "data": {"resource": resource, "context": {
            "phoneNumberId": "PNbiz", "participants": {"workspace": ["+13175550100"],
                                                       "external": list(external), "resolution": "available"}}}}).encode()
        ts = int(self.clock().timestamp())
        return self.call("POST", "/api/quo", raw, {"webhook-id": ev, "webhook-timestamp": str(ts),
                                                    "webhook-signature": sign_quo_body(raw, secret, ev, ts)})

    def val(self, method, path, body=b"", token=VAL_TOKEN):
        return self.call(method, path, body, {"Authorization": "Bearer " + token})

    def draft(self, text="Hi! Thursday at 2 works great. 🙂", **extra):
        return self.val("POST", "/api/val/drafts", dict({"to": CUSTOMER, "text": text, "category": "reply",
                                                         "customer_name": "Pat"}, **extra))

    def tap(self, action, draft_id, who=GERRIT_TG):
        self._n += 1
        return self.call("POST", "/api/telegram", {"update_id": self._n, "callback_query": {
            "id": f"cb{self._n}", "from": {"id": who}, "data": f"{action}:{draft_id}"}},
            {"X-Telegram-Bot-Api-Secret-Token": TG_SECRET})

    def reply(self, text, to_message_id=None, who=GERRIT_TG):
        self._n += 1
        msg = {"message_id": 900 + self._n, "from": {"id": who}, "chat": {"id": who}, "text": text}
        if to_message_id:
            msg["reply_to_message"] = {"message_id": to_message_id}
        return self.call("POST", "/api/telegram", {"update_id": self._n, "message": msg},
                         {"X-Telegram-Bot-Api-Secret-Token": TG_SECRET})

    def tick(self):
        return self.call("GET", "/api/tick", headers={"Authorization": "Bearer " + CRON})

    def status(self, draft_id):
        return self.store.get_draft(draft_id)["status"]


class Calls(unittest.TestCase):
    def test_missed_call_voicemail_and_summary_reach_val_once(self):
        r = Rig()
        r.quo_event("call.completed", {"id": "CA1", "direction": "incoming", "status": "unanswered",
                                       "hasVoicemail": False, "createdAt": "2026-10-20T14:00:00Z"})
        r.quo_event("call.completed", {"id": "CA2", "direction": "incoming", "status": "unanswered",
                                       "hasVoicemail": True})            # the voicemail alert covers it
        r.quo_event("call.voicemail.completed", {"id": "VM1", "callId": "CA2", "direction": "incoming",
                                                 "from": CUSTOMER, "transcript": "Hi Gerrit, call me back."})
        self.assertEqual(r.quo_event("call.voicemail.completed", {"id": "VM1", "from": CUSTOMER,
                                                                  "transcript": "again"})[1], {"duplicate": True})
        r.quo_event("call.summary.completed", {"callId": "CA3", "processingStatus": "completed",
                                               "summary": ["Asked about shutters."], "nextSteps": ["Send quote"],
                                               "fromPhoneNumber": CUSTOMER})
        _, up = r.val("GET", "/api/val/updates")
        got = {c["id"]: (c["kind"], c["text"]) for c in up["calls"]}
        self.assertEqual(got, {"CA1": ("missed", ""), "VM1": ("voicemail", "Hi Gerrit, call me back."),
                               "sum-CA3": ("call_summary", "Asked about shutters.\nNext steps:\nSend quote")})
        r.val("POST", "/api/val/ack", {"calls": ["CA1", "VM1", "sum-CA3"]})
        self.assertEqual(r.val("GET", "/api/val/updates")[1]["calls"], [])

    def test_outgoing_answered_and_unsigned_calls_are_not_kept(self):
        r = Rig()
        r.quo_event("call.completed", {"id": "CA9", "direction": "outgoing", "status": "unanswered"})
        r.quo_event("call.completed", {"id": "CA8", "direction": "incoming", "status": "answered"})
        r.quo_event("call.summary.completed", {"callId": "CA7", "processingStatus": "in-progress"})
        r.quo_event("call.completed", {"id": "CA6", "direction": "incoming", "status": "unanswered"},
                    external=("not-a-phone",))
        bad = "whsec_" + base64.b64encode(b"x" * 24).decode()
        self.assertEqual(r.quo_event("call.completed", {"id": "CA5", "direction": "incoming",
                                                        "status": "unanswered"}, secret=bad)[0], 401)
        self.assertEqual(r.val("GET", "/api/val/updates")[1]["calls"], [])

    def test_a_second_alert_key_is_accepted(self):
        second = "whsec_" + base64.b64encode(b"c" * 24).decode()
        r = Rig()
        r.bridge.cfg.quo_webhook_secret = QUO_SECRET + "," + second
        self.assertEqual(r.quo_event("call.completed", {"id": "CA1", "direction": "incoming",
                                                        "status": "unanswered"}, secret=second)[0], 200)
        self.assertEqual(len(r.val("GET", "/api/val/updates")[1]["calls"]), 1)


class Locks(unittest.TestCase):
    def test_bad_quo_signature_is_refused_and_nothing_is_stored(self):
        r = Rig()
        wrong = "whsec_" + base64.b64encode(b"x" * 24).decode()
        self.assertEqual(r.customer_texts("hi", secret=wrong)[0], 401)
        self.assertEqual(r.store.messages, {})

    def test_old_quo_alert_is_refused(self):
        r = Rig()
        raw = b'{"type":"message.received"}'
        ts = int((TUE_11AM - timedelta(minutes=10)).timestamp())
        status, _ = r.call("POST", "/api/quo", raw, {"webhook-id": "EV1", "webhook-timestamp": str(ts),
                                                       "webhook-signature": sign_quo_body(raw, QUO_SECRET, "EV1", ts)})
        self.assertEqual(status, 401)

    def test_telegram_without_the_secret_is_refused(self):
        r = Rig()
        status, _ = r.call("POST", "/api/telegram", {"callback_query": {"from": {"id": GERRIT_TG}, "data": "a:x"}})
        self.assertEqual(status, 401)

    def test_vals_code_opens_only_vals_doors(self):
        r = Rig()
        self.assertEqual(r.val("GET", "/api/val/updates")[0], 200)
        self.assertEqual(r.call("GET", "/api/tick", headers={"Authorization": "Bearer " + VAL_TOKEN})[0], 401)
        # Val can't fake a tap: the Telegram door wants Telegram's secret, not Val's code.
        self.assertEqual(r.call("POST", "/api/telegram", {}, {"Authorization": "Bearer " + VAL_TOKEN})[0], 401)
        self.assertEqual(r.call("POST", "/api/telegram", {},
                                {"X-Telegram-Bot-Api-Secret-Token": VAL_TOKEN})[0], 401)

    def test_wrong_or_missing_codes_are_refused(self):
        r = Rig()
        self.assertEqual(r.val("GET", "/api/val/updates", token="guess")[0], 401)
        self.assertEqual(r.call("GET", "/api/val/updates")[0], 401)
        self.assertEqual(r.call("POST", "/api/val/drafts", {"to": CUSTOMER, "text": "hi"},
                                {"Authorization": "Bearer " + CRON})[0], 401)
        self.assertEqual(r.quo.sent, [])

    def test_empty_secret_never_matches(self):
        r = Rig()
        r.bridge.cfg.val_token = ""
        self.assertEqual(r.call("GET", "/api/val/updates", headers={"Authorization": "Bearer "})[0], 401)

    def test_someone_else_tapping_approve_sends_nothing(self):
        r = Rig()
        r.customer_texts("Does Thursday work?")
        _, d = r.draft()
        r.tap("a", d["id"], who=999)
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.status(d["id"]), "pending")
        self.assertIn("Only Gerrit", r.tg.answers[-1])

    def test_too_big_is_refused(self):
        r = Rig()
        self.assertEqual(r.val("POST", "/api/val/drafts", b"x" * (70 * 1024))[0], 413)


class Flow(unittest.TestCase):
    def test_customer_text_reaches_val_once_with_its_thread(self):
        r = Rig()
        r.customer_texts("Hi, it's Pat. Does Thursday work?", msg_id="AC1")
        self.assertEqual(r.customer_texts("Hi, it's Pat. Does Thursday work?", msg_id="AC1")[1], {"duplicate": True})
        _, up = r.val("GET", "/api/val/updates")
        self.assertEqual([t["id"] for t in up["texts"]], ["AC1"])
        self.assertEqual(up["texts"][0]["phone"], CUSTOMER)
        self.assertEqual(up["texts"][0]["thread"][0]["text"], "Hi, it's Pat. Does Thursday work?")
        r.val("POST", "/api/val/ack", {"texts": ["AC1"]})
        self.assertEqual(r.val("GET", "/api/val/updates")[1]["texts"], [])

    def test_approve_sends_once_even_if_tapped_twice(self):
        r = Rig()
        r.customer_texts("Does Thursday work?")
        _, d = r.draft()
        self.assertEqual(d["status"], "pending")
        card = r.tg.last_card()
        self.assertEqual(card["chat"], GERRIT_TG)
        self.assertIn("Does Thursday work?", card["text"])
        self.assertIn("Hi! Thursday at 2 works great.", card["text"])
        r.tap("a", d["id"])
        r.tap("a", d["id"])
        self.assertEqual(r.quo.sent, [(CUSTOMER, "Hi! Thursday at 2 works great. 🙂")])
        self.assertEqual(r.status(d["id"]), "sent")
        self.assertIn("already did an action", r.tg.answers[-1])
        self.assertIn("✅ Sent", r.tg.edits[-1]["text"])
        # Val hears how it went, once.
        out = r.val("GET", "/api/val/updates")[1]["outcomes"]
        self.assertEqual([(o["draft_id"], o["status"], o["edited"]) for o in out], [(d["id"], "sent", False)])
        r.val("POST", "/api/val/ack", {"outcomes": [d["id"]]})
        self.assertEqual(r.val("GET", "/api/val/updates")[1]["outcomes"], [])

    def test_what_the_customer_said_comes_from_records_not_from_val(self):
        r = Rig()
        r.customer_texts("This is ridiculous. Is this a real person? How much is it?", msg_id="AC9")
        _, d = r.draft(customer_said="Sounds great, thanks!", reply_to="AC9")
        row = r.store.get_draft(d["id"])
        self.assertEqual(row["customer_said"], "This is ridiculous. Is this a real person? How much is it?")
        self.assertIn("⚠️", r.tg.last_card()["text"])

    def test_reply_to_another_customers_text_is_ignored(self):
        r = Rig()
        r.customer_texts("Call me", phone="+13175550777", msg_id="ACother")
        r.customer_texts("Thursday?", msg_id="ACmine")
        _, d = r.draft(reply_to="ACother")
        self.assertEqual(r.store.get_draft(d["id"])["reply_to"], "ACmine")

    def test_approved_at_9pm_waits_until_8am_their_time(self):
        r = Rig(now=TUE_9PM)
        _, d = r.draft()
        r.tap("a", d["id"])
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.status(d["id"]), "held")
        self.assertIn("8:00 AM", r.tg.edits[-1]["text"])
        r.clock.t = datetime(2026, 10, 21, 11, 59, tzinfo=timezone.utc)   # 7:59 am
        r.tick()
        self.assertEqual(r.quo.sent, [])
        r.clock.t = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)    # 8:00 am
        r.tick()
        r.tick()
        self.assertEqual(len(r.quo.sent), 1)
        self.assertEqual(r.status(d["id"]), "sent")

    def test_send_now_sends_a_held_text_at_once(self):
        r = Rig(now=TUE_9PM)
        _, d = r.draft()
        r.tap("a", d["id"])
        self.assertIn("n:" + d["id"], json.dumps(r.tg.edits[-1]))
        r.tap("n", d["id"])
        self.assertEqual(len(r.quo.sent), 1)
        self.assertEqual(r.status(d["id"]), "sent")
        r.tap("n", d["id"])                      # a double tap sends nothing more
        r.clock.t = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
        r.tick()
        self.assertEqual(len(r.quo.sent), 1)

    def test_only_gerrit_can_tap_send_now(self):
        r = Rig(now=TUE_9PM)
        _, d = r.draft()
        r.tap("a", d["id"])
        r.tap("n", d["id"], who=999)
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.status(d["id"]), "held")

    def test_send_now_works_only_on_a_held_text(self):
        r = Rig(now=TUE_9PM)
        _, d = r.draft()
        r.tap("n", d["id"])                      # not approved yet
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.status(d["id"]), "pending")

    def test_send_now_still_blocks_do_not_contact(self):
        r = Rig(now=TUE_9PM)
        _, d = r.draft()
        r.tap("a", d["id"])
        r.customer_texts("STOP")
        r.tap("n", d["id"])
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.status(d["id"]), "blocked")

    def test_failed_send_now_stays_held_and_can_try_again(self):
        r = Rig(now=TUE_9PM)
        _, d = r.draft()
        r.tap("a", d["id"])
        r.quo.fail_with = [QuoError("Quo refused it.", status=403)]
        r.tap("n", d["id"])
        self.assertEqual(r.status(d["id"]), "held")
        self.assertIn("n:" + d["id"], json.dumps(r.tg.edits[-1]))
        r.tap("n", d["id"])
        self.assertEqual(len(r.quo.sent), 1)
        self.assertEqual(r.status(d["id"]), "sent")

    def test_typed_message_with_one_held_text_shows_send_now(self):
        r = Rig(now=TUE_9PM)
        _, d = r.draft()
        r.tap("a", d["id"])
        r.reply("Go ahead and send now.")
        last = r.tg.sent[-1]
        self.assertIn("I cannot read typed messages", last["text"])
        self.assertIn("n:" + d["id"], json.dumps(last))
        self.assertEqual(r.quo.sent, [])         # typing alone never sends

    def test_typed_message_with_nothing_held_explains_the_buttons(self):
        r = Rig()
        r.reply("hello?")
        self.assertIn("I cannot read typed messages. Use the buttons on each draft.", r.tg.sent[-1]["text"])

    def test_held_text_can_still_be_cancelled(self):
        r = Rig(now=TUE_9PM)
        _, d = r.draft()
        r.tap("a", d["id"])
        r.tap("s", d["id"])
        r.clock.t = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
        r.tick()
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.status(d["id"]), "skipped")

    def test_skip_sends_nothing(self):
        r = Rig()
        _, d = r.draft()
        r.tap("s", d["id"])
        r.tap("a", d["id"])
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.status(d["id"]), "skipped")

    def test_edit_then_approve_sends_gerrits_words(self):
        r = Rig()
        _, d = r.draft()
        stats = r.store.save_stats("reply", 7, False)
        r.tap("e", d["id"])
        prompt = r.tg.sent[-1]
        self.assertTrue(prompt["force_reply"])
        r.reply("Thursday at 2 is perfect, see you then!", to_message_id=prompt["id"])
        self.assertEqual(r.status(d["id"]), "pending")
        self.assertIn("Your edited text", r.tg.last_card()["text"])
        r.tap("a", d["id"])
        self.assertEqual(r.quo.sent, [(CUSTOMER, "Thursday at 2 is perfect, see you then!")])
        self.assertEqual(r.store.get_stats("reply")["streak"], 0)   # an edit resets the streak
        out = r.val("GET", "/api/val/updates")[1]["outcomes"][0]
        self.assertTrue(out["edited"])
        self.assertEqual(out["val_draft"], "Hi! Thursday at 2 works great. 🙂")

    def test_a_reply_without_tapping_edit_changes_nothing(self):
        r = Rig()
        _, d = r.draft()
        r.reply("Something else")
        self.assertIsNone(r.store.get_draft(d["id"]).get("final_body"))
        self.assertIn("tap ✏️ Edit", r.tg.sent[-1]["text"])

    def test_approvals_count_toward_auto_send_once_per_draft(self):
        r = Rig()
        r.quo.fail_with = [QuoError("Quo error 500.", status=500)]
        _, d = r.draft()
        r.tap("a", d["id"])          # fails, back to pending
        self.assertEqual(r.status(d["id"]), "pending")
        r.tap("a", d["id"])          # second try sends
        self.assertEqual(r.status(d["id"]), "sent")
        self.assertEqual(r.store.get_stats("reply")["streak"], 1)


class Safety(unittest.TestCase):
    def test_stop_marks_do_not_contact_and_blocks_waiting_drafts(self):
        r = Rig()
        _, d = r.draft()
        r.customer_texts("Stop")
        self.assertTrue(r.store.is_dnc(CUSTOMER))
        self.assertEqual(r.status(d["id"]), "blocked")
        r.tap("a", d["id"])
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.draft()[0], 409)
        self.assertIn("do-not-contact", r.tg.sent[-1]["text"])
        _, up = r.val("GET", "/api/val/updates")
        self.assertTrue(up["texts"][-1]["do_not_contact"])

    def test_stop_inside_a_sentence_is_not_an_opt_out(self):
        r = Rig()
        r.customer_texts("Please stop by Thursday instead")
        self.assertFalse(r.store.is_dnc(CUSTOMER))

    def test_start_clears_do_not_contact(self):
        r = Rig()
        r.customer_texts("STOP")
        r.customer_texts("START")
        self.assertFalse(r.store.is_dnc(CUSTOMER))
        self.assertEqual(r.draft()[1]["status"], "pending")

    def test_dnc_set_after_approval_still_blocks_the_held_send(self):
        r = Rig(now=TUE_9PM)
        _, d = r.draft()
        r.tap("a", d["id"])
        r.store.set_dnc(CUSTOMER, True, "x")
        r.clock.t = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
        r.tick()
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.status(d["id"]), "blocked")

    def test_confirmations_never_make_a_card(self):
        r = Rig()
        _, d = r.draft(category="confirmation")
        self.assertEqual(d["status"], "blocked")
        self.assertEqual(r.tg.sent, [])

    def test_bad_drafts_are_refused(self):
        r = Rig()
        self.assertEqual(r.draft(to="12345")[0], 400)
        self.assertEqual(r.draft(text="")[0], 400)
        self.assertEqual(r.draft(text="x" * 1601)[0], 400)
        self.assertEqual(r.draft(category="Reply; drop")[0], 400)
        self.assertEqual(r.draft(time_zone="Mars/Base")[0], 400)
        self.assertEqual(r.tg.sent, [])

    def test_at_most_30_cards_wait_at_once(self):
        r = Rig()
        for _ in range(30):
            self.assertEqual(r.draft()[0], 200)
        self.assertEqual(r.draft()[0], 429)

    def test_quo_refusal_goes_back_to_gerrit(self):
        r = Rig()
        r.quo.fail_with = [QuoError("Quo refused it.", status=400)]
        _, d = r.draft()
        r.tap("a", d["id"])
        self.assertEqual(r.status(d["id"]), "pending")
        self.assertIn("did not send", r.tg.edits[-1]["text"])

    def test_no_answer_from_quo_says_check_before_retrying(self):
        r = Rig()
        r.quo.fail_with = [QuoError("No answer from Quo.", unknown=True)]
        _, d = r.draft()
        r.tap("a", d["id"])
        self.assertEqual(r.status(d["id"]), "failed")
        self.assertIn("Check the Quo app", r.tg.edits[-1]["text"])


class AutoSend(unittest.TestCase):
    def setUp(self):
        self.r = Rig(auto_send=True)
        self.r.store.save_stats("on_my_way", 20, True)

    def on_my_way(self, **extra):
        return self.r.draft(text="On my way, see you in 15!", category="on_my_way", prospect_id="P-1", **extra)

    def test_earned_kind_counts_down_then_sends(self):
        r = self.r
        _, d = self.on_my_way()
        self.assertEqual(d["status"], "countdown")
        self.assertIn("🛑 Stop", json.dumps(r.tg.sent[-1]["buttons"], ensure_ascii=False))
        r.clock.t += timedelta(minutes=4)
        r.tick()
        self.assertEqual(r.quo.sent, [])
        r.clock.t += timedelta(minutes=1)
        r.tick()
        self.assertEqual(r.quo.sent, [(CUSTOMER, "On my way, see you in 15!")])

    def test_stop_during_countdown_means_it_never_sends(self):
        r = self.r
        _, d = self.on_my_way()
        r.tap("x", d["id"])
        r.clock.t += timedelta(minutes=10)
        r.tick()
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.status(d["id"]), "stopped")
        self.assertFalse(r.store.get_stats("on_my_way")["enabled"])

    def test_real_person_question_always_goes_to_gerrit(self):
        r = self.r
        r.customer_texts("Is this a real person or a bot?")
        _, d = self.on_my_way()
        self.assertEqual(d["status"], "pending")

    def test_main_switch_off_means_no_countdown(self):
        r = Rig(auto_send=False)
        r.store.save_stats("on_my_way", 20, True)
        _, d = r.draft(text="On my way!", category="on_my_way", prospect_id="P-1")
        self.assertEqual(d["status"], "pending")


class Escalation(unittest.TestCase):
    def test_one_text_to_gerrits_cell_after_10_minutes(self):
        r = Rig()
        r.draft()
        r.draft()
        r.clock.t += timedelta(minutes=9)
        r.tick()
        self.assertEqual(r.quo.sent, [])
        r.clock.t += timedelta(minutes=1)
        r.tick()
        r.tick()
        self.assertEqual(r.quo.sent, [(GERRIT_CELL, "Val: 2 customer texts need your approval in Val Approvals.")])

    def test_after_2_hours_it_is_missed(self):
        r = Rig()
        _, d = r.draft()
        r.clock.t += timedelta(hours=2)
        r.tick()
        self.assertTrue(r.store.get_draft(d["id"])["missed_at"])
        self.assertEqual(r.status(d["id"]), "pending")   # still there for Gerrit

    def test_no_escalation_text_at_night_or_on_weekends(self):
        r = Rig(now=TUE_9PM)
        r.draft()
        r.clock.t += timedelta(hours=1)
        r.tick()
        r2 = Rig(now=datetime(2026, 10, 24, 16, 0, tzinfo=timezone.utc))   # Saturday noon
        r2.draft()
        r2.clock.t += timedelta(hours=1)
        r2.tick()
        self.assertEqual(r.quo.sent + r2.quo.sent, [])

    def test_failed_escalation_tries_again_next_minute(self):
        r = Rig()
        r.draft()
        r.quo.fail_with = [QuoError("Quo error 500.", status=500)]
        r.clock.t += timedelta(minutes=10)
        r.tick()
        r.clock.t += timedelta(minutes=1)
        r.tick()
        self.assertEqual(len(r.quo.sent), 1)


class Health(unittest.TestCase):
    def test_health_needs_nothing(self):
        self.assertEqual(Rig().call("GET", "/api/health"), (200, {"ok": True}))

    def test_missing_settings_fail_closed(self):
        app = wsgi.make_app(lambda: wsgi.build_bridge({}))
        got = {}
        env = {"REQUEST_METHOD": "GET", "PATH_INFO": "/api/tick", "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO()}
        b"".join(app(env, lambda s, h: got.setdefault("s", s)))
        self.assertTrue(got["s"].startswith("503"))


if __name__ == "__main__":
    unittest.main()
