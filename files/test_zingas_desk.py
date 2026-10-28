"""Tests for zingas_desk (Val's desk on the website). No network, no Hermes: fakes for both."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zingas_desk as zd  # noqa: E402
import zingas_todo as zt  # noqa: E402


class FakeSite:
    def __init__(self, answer=None):
        self.answer = answer or {"settings": {}, "version": 1, "answers": [], "messages": []}
        self.posts, self.fail = [], 0

    def get(self):
        return self.answer

    def post(self, body):
        if self.fail:
            self.fail -= 1
            raise RuntimeError("away")
        self.posts.append(body)
        return {"ok": True}

    def ops(self, op):
        return [p for p in self.posts if p["op"] == op]


class FakeHermes:
    def __init__(self):
        self.chats, self.sent, self.msgs, self.lists = [], [], {}, {"telegram": [("t", "20261028_100000_abc")],
                                                                   "cron": []}

    def sessions(self, source, limit):
        return self.lists.get(source, [])[:limit]

    def messages(self, sid):
        return self.msgs.get(sid, [])

    def chat(self, text, sid=""):
        self.chats.append((text, sid))
        return "Sure, I'll do that."

    def send(self, text):
        self.sent.append(text)

    def status(self):
        return "zingas-todo-post                 RUNNING   pid 12, uptime 1:00:00\nzingas-desk  STOPPED   Oct 28\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp()
        self.site, self.hermes = FakeSite(), FakeHermes()
        self.now = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)
        self.desk = zd.Desk(self.site, self.hermes, self.vault, clock=lambda: self.now)

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)


class SettingsTests(Base):
    def test_no_settings_means_todays_values(self):
        s = zd.settings(self.vault)
        self.assertTrue(all(s["programs"].values()))
        self.assertTrue(zd.telegram_ok("new_task", self.vault))
        r = zd.followup_rules(self.vault)
        self.assertEqual(r["touches"][0], ("48 hours", timedelta(hours=48), "both"))
        self.assertEqual((r["plan_at"], r["list_at"]), (time(7, 41), time(8, 1)))
        self.assertEqual(zd.callback_hours(self.vault)[:2], (time(9), time(19)))

    def test_odd_values_are_made_safe(self):
        s = zd.merged({"timing": {"callbackFrom": 15, "callbackTo": 10, "recordingWaitMinutes": 9999},
                       "alerts": {"note": "everywhere"},
                       "followups": {"touches": [{"key": "7 days", "days": 1}], "listAt": "3:00"}})
        self.assertEqual(s["timing"]["recordingWaitMinutes"], 240)
        self.assertGreater(s["timing"]["callbackTo"], s["timing"]["callbackFrom"])
        self.assertEqual(s["alerts"]["note"], "telegram")
        days = [t["days"] for t in s["followups"]["touches"]]
        self.assertEqual(days, sorted(set(days)))      # always going up
        self.assertEqual(s["followups"]["listAt"], "08:01")

    def test_new_version_is_saved_and_routes_follow_it(self):
        self.site.answer = {"version": 4, "answers": [], "messages": [], "settings": {
            "programs": {"hotleads": False}, "alerts": {"new_task": "ipad"},
            "followups": {"touches": [{"key": "day 14", "on": False}], "quietDays": 5, "listAt": "09:30"}}}
        self.desk.step()
        self.assertFalse(zd.program_on("hotleads", self.vault))
        self.assertTrue(zd.program_on("thanks", self.vault))
        self.assertFalse(zd.telegram_ok("new_task", self.vault))
        r = zd.followup_rules(self.vault)
        self.assertNotIn("day 14", [k for k, _, _ in r["touches"]])
        self.assertEqual((r["quiet"], r["list_at"], r["plan_at"]), (timedelta(days=5), time(9, 30), time(9, 10)))

    def test_answers_and_links_reach_val(self):
        import value_answers as va
        import zingas_installs as zi
        self.site.answer = {"version": 2, "answers": [], "messages": [], "settings": {
            "answers": {"costco": "We measure, install and stand behind it for life."},
            "links": {"reviewLink": "https://g.page/r/zingas/review", "referralReward": "a $50 card"}}}
        self.desk.step()
        self.assertEqual(va.load(self.vault)["costco"], "We measure, install and stand behind it for life.")
        cfg = zi.settings(self.vault)
        self.assertEqual(cfg["review_link"], "https://g.page/r/zingas/review")
        self.assertNotIn("referral", cfg)               # an amount never goes in a text

    def test_a_telegram_change_survives_until_the_same_topic_changes_on_the_website(self):
        import value_answers as va
        self.site.answer = {"version": 2, "answers": [], "messages": [], "settings": {"answers": {"price": "A"}}}
        self.desk.step()
        va.save(dict(va.load(self.vault), price="B from Telegram"), self.vault)
        self.site.answer = {"version": 3, "answers": [], "messages": [],
                            "settings": {"answers": {"price": "A", "costco": "C"}}}
        self.desk.step()
        self.assertEqual(va.load(self.vault)["price"], "B from Telegram")
        self.assertEqual(va.load(self.vault)["costco"], "C")

    def test_first_sync_seeds_the_website(self):
        import value_answers as va
        va.save({"general": "Local, family owned."}, self.vault)
        self.desk.step()
        seed = self.site.ops("seed")[0]
        self.assertEqual(seed["answers"], {"general": "Local, family owned."})
        self.desk.step()
        self.assertEqual(len(self.site.ops("seed")), 1)


class OutboxTests(Base):
    def test_notes_go_in_one_batch_and_wait_when_the_website_is_away(self):
        zd.note("new_task", "📝 New task", vault=self.vault)
        zd.note("hot_lead", "🔥 Pat signed", vault=self.vault)
        self.site.fail = 1
        self.assertEqual(self.desk.flush(), 0)
        self.assertEqual(len(zd.take_outbox(self.vault)), 2)
        self.assertEqual(self.desk.flush(), 2)
        notes = self.site.ops("note")[0]["notes"]
        self.assertEqual([n["kind"] for n in notes], ["new_task", "hot_lead"])
        self.assertEqual(zd.take_outbox(self.vault), [])

    def test_a_note_never_raises(self):
        self.assertFalse(zd.note("note", "x", vault="/proc/no/such/place"))

    def test_same_question_same_id(self):
        self.assertEqual(zd.question_id("related_done", "a,b"), zd.question_id("related_done", "a,b"))


class RelatedDoneTests(Base):
    def setUp(self):
        super().setUp()
        self.todo = zt.TodoList(self.vault)
        self.a = self.todo.add("Call back about the shades", who="Pat Lee")
        self.b = self.todo.add("Send Lee the samples", who="Pat Lee")

    def test_done_asks_on_the_website_and_yes_closes_the_task(self):
        sent = []
        orig = zt.subprocess.run
        zt.subprocess.run = lambda *a, **k: sent.append(k.get("input"))
        try:
            closed = [self.todo.close_id(self.a["id"])]
            zt.after_done(self.todo, closed)
        finally:
            zt.subprocess.run = orig
        self.assertTrue(any("done too" in (t or "") for t in sent))      # Telegram still asks
        self.desk.flush()
        q = self.site.ops("ask")[0]["question"]
        self.assertEqual([o["key"] for o in q["options"]], ["yes", "no"])
        self.site.posts.clear()
        self.site.answer = {"version": 1, "settings": {}, "messages": [],
                            "answers": [{"id": q["id"], "kind": "related_done", "answer": "yes", "label": "Yes"}]}
        zt.subprocess.run = lambda *a, **k: None
        try:
            self.desk.step()
        finally:
            zt.subprocess.run = orig
        self.assertNotIn(self.b["id"], [i["id"] for i in self.todo.open_items()])
        self.assertEqual(self.site.ops("close")[0]["note"], "Marked done.")

    def test_done_in_telegram_closes_the_card(self):
        self.desk.st["asked"]["related_done:x"] = {"kind": "related_done", "meta": {"ids": [self.b["id"]]}}
        self.todo.close_id(self.b["id"])
        self.assertEqual(self.desk.close_done_elsewhere(), 1)
        self.desk.flush()
        self.assertEqual(self.site.ops("close")[0]["note"], "Done in Telegram.")


class TalkTests(Base):
    def test_a_website_message_goes_into_the_telegram_conversation(self):
        self.site.answer = {"version": 1, "settings": {}, "answers": [],
                            "messages": [{"id": "m1", "text": "Move Pat to Friday", "at": "x"}]}
        self.desk.step()
        text, sid = self.hermes.chats[0]
        self.assertTrue(text.startswith(zd.WEB_MARK))
        self.assertEqual(sid, "20261028_100000_abc")
        self.assertIn("Move Pat to Friday", self.hermes.sent[0])
        self.assertEqual(self.site.ops("taken")[0]["messages"], ["m1"])
        self.assertEqual(self.site.ops("replied")[0]["results"][0]["ok"], True)
        self.assertEqual(self.site.ops("turns")[0]["turns"][0]["author"], "val")

    def test_mirror_copies_new_telegram_turns_but_not_the_websites(self):
        sid = "20261028_100000_abc"
        self.hermes.msgs[sid] = [
            {"id": 1, "role": "user", "content": "show my list", "timestamp": 1761660000},
            {"id": 2, "role": "assistant", "content": "", "tool_calls": [{}]},
            {"id": 3, "role": "tool", "content": "{}"},
            {"id": 4, "role": "assistant", "content": "Here it is", "timestamp": 1761660005},
            {"id": 5, "role": "user", "content": zd.WEB_MARK + "Gerrit wrote on the website: hi"},
        ]
        self.assertEqual(self.desk.mirror(), 2)
        turns = self.site.ops("turns")[0]["turns"]
        self.assertEqual([t["author"] for t in turns], ["gerrit", "val"])
        self.assertEqual(turns[0]["id"], f"tg:{sid}:1")
        self.hermes.msgs[sid].append({"id": 6, "role": "user", "content": "thanks"})
        self.assertEqual(self.desk.mirror(), 1)


class BriefAndHealthTests(Base):
    def test_brief_is_copied_once(self):
        sid = "cron_0ed663bc7090_20261028_080054"
        self.hermes.lists["cron"] = [("zingas-morning-brief · Oct 28  /briefs  10h ago  " + sid, sid)]
        self.hermes.msgs[sid] = [{"id": 1, "role": "user", "content": "/briefs"},
                                 {"id": 2, "role": "assistant", "content": "☀️ Good morning", "timestamp": 1761652854}]
        self.assertEqual(self.desk.briefs(), 1)
        b = self.site.ops("brief")[0]["brief"]
        self.assertEqual((b["kind"], b["day"]), ("morning", "2026-10-28"))
        self.assertEqual(self.desk.briefs(), 0)

    def test_health_lists_programs(self):
        self.desk.health()
        h = self.site.ops("health")[0]["health"]
        self.assertEqual(h["programs"], [{"name": "zingas-todo-post", "state": "running"},
                                         {"name": "zingas-desk", "state": "stopped"}])


class TellTests(Base):
    def test_ipad_only_kind_skips_telegram_but_keeps_the_note(self):
        zd._save(zd.paths(self.vault)["settings"], {"version": 1, "settings": {"alerts": {"hot_lead": "ipad"}}})
        orig_vault, sent = zd.VAULT, []
        zd.VAULT = self.vault
        orig = zt.subprocess.run
        zt.subprocess.run = lambda *a, **k: sent.append(k.get("input"))
        try:
            zt.tell_gerrit("🔥 Pat signed", "hot_lead")
            zt.tell_gerrit("📝 New task", "new_task")
        finally:
            zd.VAULT, zt.subprocess.run = orig_vault, orig
        self.assertEqual(sent, ["📝 New task"])
        self.assertEqual([e["note"]["kind"] for e in zd.take_outbox(self.vault)], ["hot_lead", "new_task"])


class FollowupRulesTests(Base):
    def test_rules_move_touches_turn_them_off_and_pick_the_channel(self):
        import zingas_followups as zf
        from test_zingas_followups import appt_msg, at, z
        a = zf.parse_appointment(appt_msg("a1", at(2026, 10, 19, 15, 0), "Pat Testerson"))
        est = {"email": "pat@example.com", "sent_at": z(at(2026, 10, 20, 10)), "msg_id": "e1", "pdfs": []}
        f = zf.Followups(None, None, vault=self.vault, clock=lambda: at(2026, 10, 20, 11))
        c = zf.new_customer(est, a, at(2026, 10, 20, 11))
        f.st["customers"][c["email"]] = c
        self.assertEqual(f.sync_rules(), 0)                       # nothing saved on the website yet: no change
        zd._save(zd.paths(self.vault)["settings"], {"version": 2, "settings": {"followups": {
            "touches": [{"key": "48 hours", "days": 3, "send": "text"}, {"key": "7 days", "on": False},
                        {"key": "day 14", "send": "email"}], "quietDays": 6}}})
        self.assertGreater(f.sync_rules(), 0)
        t = c["touches"]
        self.assertEqual(zf.parse_iso(t["48 hours"]["due"]), at(2026, 10, 22, 15, 0))
        self.assertTrue(t["7 days"].get("off"))
        self.assertEqual((f.channels("48 hours", "+13175550142"), f.channels("48 hours", "")), ("text", "email"))
        self.assertEqual(f.channels("day 14", "+13175550142"), "email")
        self.assertEqual(f.silence(), timedelta(days=6))
        zd._save(zd.paths(self.vault)["settings"], {"version": 3, "settings": {}})
        f.sync_rules()
        self.assertNotIn("off", t["7 days"])                      # back on when he turns it on
        self.assertEqual(zf.parse_iso(t["48 hours"]["due"]), at(2026, 10, 21, 15, 0))


if __name__ == "__main__":
    unittest.main()
