"""Val's activity log door and the watchdog that texts Gerrit (activity.py). Fake Quo, fixed clock."""

import unittest
from datetime import datetime, timedelta, timezone

from clients import QuoError
from store import SupabaseStore
from test_bridge import CRON, GERRIT_CELL, Rig

MON_640AM = datetime(2026, 10, 26, 10, 40, tzinfo=timezone.utc)    # Monday 6:40 am in Indianapolis
MON_8AM = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
SAT_9AM = datetime(2026, 10, 24, 13, 0, tzinfo=timezone.utc)


class Door(unittest.TestCase):
    def test_lines_and_checkin_are_saved(self):
        r = Rig(now=MON_8AM)
        st, body = r.val("POST", "/api/val/activity", {
            "checkin": "all 10 running",
            "events": [{"program": "followups", "at": "2026-10-26T11:40:00+00:00", "line": "list made for 2026-10-26: 7"},
                       {"program": "backup", "line": "backup ok"}]})
        self.assertEqual((st, body), (200, {"saved": 3}))
        kinds = [(e["kind"], e["detail"]) for e in r.store.events]
        self.assertIn(("val:followups", "list made for 2026-10-26: 7"), kinds)
        self.assertIn(("val:backup", "backup ok"), kinds)
        self.assertIn(("val:checkin", "all 10 running"), kinds)
        fu = [e for e in r.store.events if e["kind"] == "val:followups"][0]
        self.assertTrue(fu["at"].startswith("2026-10-26T11:40"))

    def test_needs_vals_code(self):
        r = Rig(now=MON_8AM)
        st, _ = r.val("POST", "/api/val/activity", {"checkin": "x"}, token="wrong")
        self.assertEqual(st, 401)
        st, _ = r.call("POST", "/api/val/activity", {"checkin": "x"}, {"Authorization": "Bearer " + CRON})
        self.assertEqual(st, 401)
        self.assertEqual(r.store.events, [])

    def test_bad_input_is_refused(self):
        r = Rig(now=MON_8AM)
        self.assertEqual(r.val("POST", "/api/val/activity", {"events": [{"program": "Bad Name!", "line": "x"}]})[0], 400)
        self.assertEqual(r.val("POST", "/api/val/activity", {"events": "x"})[0], 400)
        self.assertEqual(r.val("POST", "/api/val/activity",
                               {"events": [{"program": "a", "line": "x"}] * 101})[0], 400)
        self.assertEqual(r.store.events, [])

    def test_long_lines_are_cut_and_odd_times_become_now(self):
        r = Rig(now=MON_8AM)
        r.val("POST", "/api/val/activity", {"events": [
            {"program": "inbox", "line": "a" * 1000 + "\x00", "at": "2030-01-01T00:00:00+00:00"},
            {"program": "inbox", "line": "   "}]})
        self.assertEqual(len(r.store.events), 1)
        e = r.store.events[0]
        self.assertEqual(len(e["detail"]), 300)
        self.assertTrue(e["at"].startswith("2026-10-26T12:00"))


class Watchdog(unittest.TestCase):
    def checkin(self, r, detail="all 10 running"):
        r.val("POST", "/api/val/activity", {"checkin": detail})

    def list_made(self, r, day="2026-10-26"):
        r.val("POST", "/api/val/activity", {"events": [{"program": "followups", "line": f"list made for {day}: 3"}]})

    def texts(self, r):
        return [t for to, t in r.quo.sent if to == GERRIT_CELL]

    def test_quiet_before_val_ever_checks_in(self):
        r = Rig(now=MON_8AM + timedelta(hours=3))
        r.tick()
        self.assertEqual(r.quo.sent, [])

    def test_down_waits_for_7am_then_texts_once_then_back(self):
        r = Rig(now=MON_640AM - timedelta(hours=1, minutes=10))     # 5:30 am
        self.checkin(r)
        r.clock.t = MON_640AM                                     # 6:40: down, but too early to text
        r.tick()
        self.assertEqual(self.texts(r), [])
        r.clock.t = MON_640AM + timedelta(minutes=20)             # 7:00
        r.tick()
        r.tick()
        sent = self.texts(r)
        self.assertEqual(len(sent), 1)
        self.assertIn("hasn't checked in since 5:30 AM", sent[0])
        r.clock.t += timedelta(hours=5)                           # still down at noon: no new text
        r.tick()
        self.assertEqual(len(self.texts(r)), 1)
        self.checkin(r)                                           # back
        r.tick()
        self.assertEqual(len(self.texts(r)), 2)
        self.assertIn("Val is back", self.texts(r)[1])
        r.tick()
        self.assertEqual(len(self.texts(r)), 2)

    def test_down_again_later_texts_again(self):
        r = Rig(now=MON_8AM)
        self.checkin(r)
        r.clock.t += timedelta(minutes=31)
        r.tick()
        self.checkin(r)
        r.tick()
        r.clock.t += timedelta(minutes=31)
        r.tick()
        self.assertEqual([t.split(":")[1].split(".")[0].strip()[:12] for t in self.texts(r)],
                         ["Val hasn't c", "Val is back", "Val hasn't c"])

    def test_no_follow_up_list_by_810_on_a_weekday(self):
        r = Rig(now=MON_8AM + timedelta(minutes=5))              # 8:05: not yet
        self.checkin(r)
        r.tick()
        self.assertEqual(self.texts(r), [])
        r.clock.t = MON_8AM + timedelta(minutes=10)
        self.checkin(r)
        r.tick()
        r.tick()
        self.assertEqual(len(self.texts(r)), 1)
        self.assertIn("follow-up list", self.texts(r)[0])

    def test_list_made_means_no_text(self):
        r = Rig(now=MON_8AM + timedelta(minutes=30))
        self.list_made(r)
        self.checkin(r)
        r.tick()
        self.assertEqual(self.texts(r), [])

    def test_yesterdays_list_does_not_count_and_weekends_have_no_list(self):
        r = Rig(now=MON_8AM + timedelta(minutes=30))
        self.list_made(r, day="2026-10-23")
        self.checkin(r)
        r.tick()
        self.assertEqual(len(self.texts(r)), 1)
        w = Rig(now=SAT_9AM)
        self.checkin(w)
        w.tick()
        self.assertEqual(self.texts(w), [])

    def test_no_list_text_right_after_val_comes_back(self):
        r = Rig(now=MON_8AM - timedelta(hours=2))
        self.checkin(r)
        r.clock.t = MON_8AM + timedelta(hours=4)                   # noon: down text
        r.tick()
        self.checkin(r)                                           # back; her list follows a minute later
        r.tick()
        self.assertEqual(len(self.texts(r)), 2)
        r.clock.t += timedelta(minutes=1)
        self.checkin(r)
        r.tick()
        self.assertEqual(len(self.texts(r)), 2)
        r.clock.t += timedelta(minutes=1)
        self.list_made(r)
        r.clock.t += timedelta(minutes=20)
        self.checkin(r)
        r.tick()
        self.assertEqual(len(self.texts(r)), 2)

    def test_program_stopped_30_minutes_texts_once_a_day(self):
        r = Rig(now=SAT_9AM)
        self.checkin(r, "stopped 30+ min: zingas-inbox")
        r.tick()
        r.tick()
        self.assertEqual(len(self.texts(r)), 1)
        self.assertIn("zingas-inbox stopped", self.texts(r)[0])
        self.checkin(r, "stopped 30+ min: zingas-inbox, zingas-money")
        r.tick()
        self.assertEqual(len(self.texts(r)), 2)

    def test_no_cell_no_texts_and_quo_failure_tries_again(self):
        r = Rig(now=MON_8AM, gerrit_cell="")
        self.checkin(r)
        r.clock.t += timedelta(hours=1)
        r.tick()
        self.assertEqual(r.quo.sent, [])
        r = Rig(now=MON_8AM)
        self.checkin(r)
        r.clock.t += timedelta(hours=1)
        r.quo.fail_with = [QuoError("quo down")]
        r.tick()
        self.assertEqual(self.texts(r), [])
        r.tick()
        self.assertEqual(len(self.texts(r)), 1)

    def test_watchdog_error_never_stops_the_timer(self):
        r = Rig(now=MON_8AM)
        self.checkin(r)
        r.store.last_event = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db"))
        st, body = r.tick()
        self.assertEqual(st, 200)


class SupabaseQueries(unittest.TestCase):
    def test_last_event_asks_for_the_newest_matching_row(self):
        s = SupabaseStore("https://x.supabase.co", "sb_secret_x")
        seen = []
        s._call = lambda method, path, body=None, prefer="": seen.append((method, path)) or []
        self.assertIsNone(s.last_event("val:followups", "list made for 2026-10-26"))
        s.last_event("watchdog", "100%_done*")
        s.log_many([{"at": "t", "kind": "val:x", "detail": "y"}])
        self.assertEqual(seen[0], ("GET", "events?kind=eq.val%3Afollowups&detail=like.list%20made%20for%202026-10-26%2A"
                                          "&select=at,detail&order=at.desc&limit=1"))
        self.assertIn("detail=like.100__done_%2A", seen[1][1])
        self.assertEqual(seen[2][0], "POST")


if __name__ == "__main__":
    unittest.main()
