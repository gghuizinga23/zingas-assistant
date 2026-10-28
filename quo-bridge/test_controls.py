"""Tests for Gerrit's switches on the website (Assistant > Settings) as quo-bridge sees them: Pause all customer
texts, the website's auto-send switch, the auto-send and activity doors, and watchdog notes. Nothing reaches the
internet: the website link is a fake, or urlopen is swapped (test_os_link.FakeNet)."""

import unittest
from datetime import timedelta
from unittest import mock

import activity
import os_link
from bridge import PAUSED_NOTE, mask_contact
from os_link import OsLink
from test_bridge import CUSTOMER, GERRIT_CELL, Rig
from test_os_link import OS_TOKEN, OS_URL, Clock, FakeNet, http_error


class FakeLink:
    def __init__(self, paused=False, auto_send=True):
        self.state = {"paused": paused, "autoSend": auto_send}
        self.notes = []

    def controls(self):
        return dict(self.state)

    def note(self, kind, text):
        self.notes.append((kind, text))
        return True


def rig(paused=False, auto_send_site=True, **kw):
    r = Rig(**kw)
    r.link = r.store.link = FakeLink(paused, auto_send_site)
    r.bridge.cfg.os_token = OS_TOKEN
    return r


def os_call(r, method, path, body=b""):
    return r.call(method, path, body, {"Authorization": "Bearer " + OS_TOKEN})


class Pause(unittest.TestCase):
    def test_paused_approval_waits_then_sends_once_back_on(self):
        r = rig(paused=True)
        r.customer_texts("Can you come Thursday?")
        _, d = r.draft()
        r.tap("a", d["id"])
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.status(d["id"]), "held")
        self.assertIn("paused", r.tg.edits[-1]["text"])
        edits = len(r.tg.edits)
        r.clock.t += timedelta(minutes=2)
        r.tick()                                       # still paused: no send, and no new card edit
        self.assertEqual((r.quo.sent, len(r.tg.edits)), ([], edits))
        r.link.state["paused"] = False
        r.clock.t += timedelta(minutes=2)
        r.tick()
        self.assertEqual(r.quo.sent, [(CUSTOMER, "Hi! Thursday at 2 works great. 🙂")])
        self.assertEqual(r.status(d["id"]), "sent")

    def test_auto_send_while_paused_goes_back_to_gerrit(self):
        r = rig(paused=False, auto_send=True)
        r.store.save_stats("on_my_way", 20, True)
        _, d = r.draft(text="On my way!", category="on_my_way", prospect_id="P-1")
        self.assertEqual(d["status"], "countdown")
        r.link.state["paused"] = True
        r.clock.t += timedelta(minutes=6)
        r.tick()
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.status(d["id"]), "pending")
        self.assertEqual(r.store.get_draft(d["id"])["reasons"], PAUSED_NOTE)

    def test_paused_followup_stays_approved(self):
        from test_followups import DAY, Base, followup_id, item
        b = Base()
        r = b.rig()
        r.link = r.store.link = FakeLink(paused=True)
        b.submit(r, [item()])
        fid = followup_id("pat@example.com", "48 hours", DAY)
        r.tap("fa", DAY)
        r.clock.t += timedelta(hours=3)                 # past its time, but paused
        r.tick()
        self.assertEqual(r.quo.sent, [])
        self.assertEqual(r.status(fid), "held")
        r.link.state["paused"] = False
        r.clock.t += timedelta(minutes=2)
        r.tick()
        self.assertEqual(len(r.quo.sent), 1)


class AutoSendSwitches(unittest.TestCase):
    def test_website_switch_off_means_no_countdown(self):
        r = rig(auto_send=True, auto_send_site=False)
        r.store.save_stats("on_my_way", 20, True)
        _, d = r.draft(text="On my way!", category="on_my_way", prospect_id="P-1")
        self.assertEqual(d["status"], "pending")

    def test_door_shows_progress_and_turns_a_kind_off(self):
        r = rig(auto_send=True)
        r.store.save_stats("followup", 14, False)
        r.store.save_stats("on_my_way", 20, True)
        status, body = os_call(r, "GET", "/api/os/autosend")
        self.assertEqual((status, body["envOn"], body["websiteOn"]), (200, True, True))
        kinds = {k["category"]: k for k in body["kinds"]}
        self.assertEqual((kinds["followup"]["streak"], kinds["followup"]["enabled"]), (14, False))
        self.assertTrue(kinds["on_my_way"]["enabled"])
        status, body = os_call(r, "POST", "/api/os/autosend", {"category": "on_my_way", "enabled": False})
        self.assertEqual(status, 200)
        self.assertEqual(r.store.get_stats("on_my_way"), {"category": "on_my_way", "streak": 0, "enabled": False})
        # the website can never turn one on, and only knows the auto-send kinds
        self.assertEqual(os_call(r, "POST", "/api/os/autosend", {"category": "on_my_way", "enabled": True})[0], 400)
        self.assertEqual(os_call(r, "POST", "/api/os/autosend", {"category": "confirmation", "enabled": False})[0], 400)

    def test_doors_need_the_website_code(self):
        r = rig()
        self.assertEqual(r.call("GET", "/api/os/autosend")[0], 401)
        self.assertEqual(r.val("GET", "/api/os/activity")[0], 401)


class Activity(unittest.TestCase):
    def test_newest_first_with_phones_and_emails_masked(self):
        r = rig()
        r.store.log("val:followups", None, "list made for 2026-10-28", "2026-10-28T11:40:00Z")
        r.store.log("followups_stopped", "x", "pat.lee@gmail.com +1 (317) 555-0123", "2026-10-28T12:00:00Z")
        r.store.log("cost_posted", None, "noise", "2026-10-28T12:05:00Z")
        r.store.log("val:checkin", None, "running: followups, thanks", "2026-10-28T12:10:00Z")
        r.clock.t = r.clock.t.replace(year=2026, month=10, day=28, hour=13)
        status, body = os_call(r, "GET", "/api/os/activity")
        self.assertEqual(status, 200)
        kinds = [e["kind"] for e in body["events"]]
        self.assertEqual(kinds[0], "val:checkin")
        self.assertNotIn("cost_posted", kinds)
        stopped = next(e for e in body["events"] if e["kind"] == "followups_stopped")
        self.assertEqual(stopped["detail"], "p…@gmail.com …0123")
        self.assertEqual(body["checkin"]["detail"], "running: followups, thanks")

    def test_mask(self):
        self.assertEqual(mask_contact("call 3175550123 now"), "call …0123 now")
        self.assertEqual(mask_contact("no numbers 12 34"), "no numbers 12 34")


class WatchdogNote(unittest.TestCase):
    def test_alert_also_goes_to_the_website(self):
        r = rig()
        r.store.log("val:checkin", None, "running", "2026-10-28T10:00:00Z")
        r.clock.t = r.clock.t.replace(year=2026, month=10, day=28, hour=15)   # 11 AM Indianapolis, 5 hours later
        r.tick()
        self.assertTrue(any(c[0] == GERRIT_CELL for c in r.quo.sent))
        self.assertEqual(r.link.notes[0][0], "watchdog")
        self.assertIn("hasn't checked in", r.link.notes[0][1])


class LinkControls(unittest.TestCase):
    def test_reads_and_caches_the_switches(self):
        clock = Clock()
        net = FakeNet(b'{"paused": true, "autoSend": false}', b'{"paused": false, "autoSend": true}')
        link = OsLink(OS_URL, OS_TOKEN, clock=clock)
        with mock.patch("urllib.request.urlopen", net):
            self.assertEqual(link.controls(), {"paused": True, "autoSend": False})
            clock.t += 5
            self.assertEqual(link.controls()["paused"], True)          # cached
            clock.t += 20
            self.assertEqual(link.controls(), {"paused": False, "autoSend": True})
        self.assertEqual(len(net.requests), 2)
        self.assertTrue(net.requests[0]["url"].endswith("/api/assistant/contact?controls=1"))
        self.assertEqual(net.requests[0]["headers"]["authorization"], "Bearer " + OS_TOKEN)

    def test_unsure_counts_as_paused(self):
        link = OsLink(OS_URL, OS_TOKEN, clock=Clock())
        with mock.patch("urllib.request.urlopen", FakeNet(http_error(502))), mock.patch.object(os_link, "_warn"):
            self.assertTrue(link.controls()["paused"])
        with mock.patch("urllib.request.urlopen", FakeNet(b'{"doNotContact": false}')), mock.patch.object(os_link, "_warn"):
            link2 = OsLink(OS_URL, OS_TOKEN, clock=Clock())
            self.assertTrue(link2.controls()["paused"])                  # no "paused" in the answer

    def test_note_posts_to_the_desk(self):
        net = FakeNet(b'{"ok": true}')
        with mock.patch("urllib.request.urlopen", net):
            self.assertTrue(OsLink(OS_URL, OS_TOKEN, clock=Clock()).note("watchdog", "Val is down"))
        self.assertTrue(net.requests[0]["url"].endswith("/api/assistant/desk"))
        self.assertEqual(net.requests[0]["body"], {"op": "note", "notes": [{"kind": "watchdog", "text": "Val is down"}]})


if __name__ == "__main__":
    unittest.main()
