"""Val's activity sender (zingas_activity.py): temp files, a fake quo-bridge, a fixed clock."""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import zingas_activity as za

T0 = datetime(2026, 10, 26, 16, 0, tzinfo=timezone.utc)


class FakeSender:
    def __init__(self):
        self.calls, self.fail = [], False

    def send(self, events, checkin):
        if self.fail:
            raise RuntimeError("quo-bridge: HTTP 503")
        self.calls.append((list(events), checkin))

    def lines(self):
        return [e["line"] for evs, _ in self.calls for e in evs]

    def checkins(self):
        return [c for _, c in self.calls if c is not None]


class Rig:
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="act-test-")
        self.logs = os.path.join(self.dir, "logs")
        os.makedirs(self.logs)
        os.makedirs(os.path.join(self.dir, "followups"))
        os.makedirs(os.path.join(self.dir, "todo"))
        self.sender = FakeSender()
        self.now = T0
        self.programs = {"hermes-gateway": "RUNNING", "zingas-inbox": "RUNNING"}
        self.make()

    def make(self):
        self.act = za.Activity(self.sender, log_glob=os.path.join(self.logs, "zingas-*"),
                               state_path=os.path.join(self.dir, "state.json"),
                               plan_path=os.path.join(self.dir, "followups", "state.json"),
                               brief_path=os.path.join(self.dir, "todo", "last-brief.txt"),
                               status=lambda: dict(self.programs), clock=lambda: self.now)

    def write(self, name, text):
        with open(os.path.join(self.logs, name), "a") as fh:
            fh.write(text)

    def plan(self, day, n, made_at):
        with open(os.path.join(self.dir, "followups", "state.json"), "w") as fh:
            json.dump({"plan": {"day": day, "items": [{}] * n, "made_at": made_at}}, fh)

    def brief(self, stamp):
        with open(os.path.join(self.dir, "todo", "last-brief.txt"), "w") as fh:
            fh.write(stamp)

    def done(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class Sending(unittest.TestCase):
    def setUp(self):
        self.r = Rig()

    def tearDown(self):
        self.r.done()

    def test_first_run_skips_old_lines_then_sends_new_ones(self):
        r = self.r
        r.write("zingas-followups.log", "2026-10-25T09:00:00+00:00 done old\n")
        r.act.step()
        self.assertEqual(r.sender.lines(), [])
        self.assertEqual(r.sender.checkins(), ["all 2 running"])
        r.write("zingas-followups.log", "2026-10-26T16:00:30+00:00 done {'plan': 7}\n")
        r.write("zingas-backup.err", "Traceback boom\n")
        r.now += timedelta(minutes=1)
        r.act.step()
        evs = r.sender.calls[-1][0]
        self.assertIn({"program": "followups", "at": "2026-10-26T16:00:30+00:00", "line": "done {'plan': 7}"}, evs)
        self.assertIn({"program": "backup", "at": "", "line": "ERR Traceback boom"}, evs)
        self.assertIsNone(r.sender.calls[-1][1])          # no check-in again before 10 minutes

    def test_half_lines_wait_and_nothing_is_sent_twice(self):
        r = self.r
        r.act.step()
        r.write("zingas-inbox.log", "first line\nsecond hal")
        r.act.step()
        r.write("zingas-inbox.log", "f\n")
        r.act.step()
        r.act.step()
        self.assertEqual(r.sender.lines(), ["first line", "second half"])

    def test_quo_bridge_down_keeps_the_place(self):
        r = self.r
        r.act.step()
        r.write("zingas-inbox.log", "one\n")
        r.sender.fail = True
        with self.assertRaises(RuntimeError):
            r.act.step()
        r.sender.fail = False
        r.make()                                       # the loop starts fresh after an error
        r.act.step()
        self.assertEqual(r.sender.lines(), ["one"])

    def test_rotated_log_starts_from_the_top(self):
        r = self.r
        r.write("zingas-inbox.log", "a long line before rotation\n")
        r.act.step()
        os.remove(os.path.join(r.logs, "zingas-inbox.log"))
        r.write("zingas-inbox.log", "new\n")
        r.act.step()
        self.assertEqual(r.sender.lines(), ["new"])

    def test_new_program_log_is_read_from_the_top(self):
        r = self.r
        r.act.step()
        r.write("zingas-plaud.log", "hello\n")
        r.act.step()
        self.assertEqual(r.sender.lines(), ["hello"])

    def test_own_log_and_heartbeat_ok_lines_are_skipped(self):
        r = self.r
        r.act.step()
        r.write("zingas-activity.log", "me\n")
        r.write("zingas-heartbeat.log", "2026-10-26T16:00:00+00:00 ok\n2026-10-26T16:10:00+00:00 ping failed\n")
        r.act.step()
        self.assertEqual(r.sender.lines(), ["ping failed"])

    def test_flood_is_capped(self):
        r = self.r
        r.act.step()
        r.write("zingas-inbox.log", "".join(f"line {i}\n" for i in range(100)))
        r.act.step()
        lines = r.sender.lines()
        self.assertEqual(len(lines), za.LINES_MAX + 1)
        self.assertEqual(lines[-1], "(+60 more lines not sent)")


class Milestones(unittest.TestCase):
    def setUp(self):
        self.r = Rig()

    def tearDown(self):
        self.r.done()

    def test_list_made_is_reported_once_even_with_no_items(self):
        r = self.r
        r.plan("2026-10-26", 7, "2026-10-26T12:52:47-04:00")
        r.act.step()
        r.act.step()
        self.assertEqual(r.sender.lines(), ["list made for 2026-10-26: 7 follow-ups"])
        r.plan("2026-10-27", 0, "2026-10-27T07:40:05-04:00")
        r.act.step()
        self.assertEqual(r.sender.lines()[-1], "list made for 2026-10-27: 0 follow-ups")

    def test_brief_made_after_the_first_look(self):
        r = self.r
        r.brief("2026-10-26T08:00:03")
        r.act.step()
        self.assertEqual(r.sender.lines(), [])
        r.brief("2026-10-26T19:30:01")
        r.act.step()
        self.assertEqual(r.sender.lines(), ["brief made (stamp 2026-10-26T19:30:01)"])


class Checkin(unittest.TestCase):
    def setUp(self):
        self.r = Rig()

    def tearDown(self):
        self.r.done()

    def test_every_10_minutes_and_stopped_programs(self):
        r = self.r
        r.act.step()
        r.programs["zingas-inbox"] = "FATAL"
        r.now += timedelta(minutes=5)
        r.act.step()
        self.assertEqual(r.sender.checkins(), ["all 2 running"])
        r.now += timedelta(minutes=5)
        r.act.step()
        self.assertEqual(r.sender.checkins()[-1], "1 of 2 running; just stopped: zingas-inbox")
        r.now += timedelta(minutes=30)
        r.act.step()
        self.assertEqual(r.sender.checkins()[-1], "stopped 30+ min: zingas-inbox")
        r.programs["zingas-inbox"] = "RUNNING"
        r.now += timedelta(minutes=10)
        r.act.step()
        self.assertEqual(r.sender.checkins()[-1], "all 2 running")

    def test_no_status_says_so(self):
        r = self.r
        r.programs = {}
        r.act.step()
        self.assertEqual(r.sender.checkins(), ["can't read program status (supervisorctl)"])


class Settings(unittest.TestCase):
    def test_reads_url_and_code_and_wants_https(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "quo-bridge.env")
            self.assertIsNone(za.sender_from_env(p))
            with open(p, "w") as fh:
                fh.write("QUO_BRIDGE_URL=https://example.vercel.app\nVAL_DRAFT_TOKEN=abc\n")
            s = za.sender_from_env(p)
            self.assertEqual((s.url, s.token), ("https://example.vercel.app", "abc"))
            with self.assertRaises(ValueError):
                za.Sender("http://example.com", "x")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_program_names(self):
        self.assertEqual(za.program_of("/var/log/orgo/zingas-quo-pickup.err"), "quo-pickup")
        self.assertEqual(za.split_line("2026-10-26T16:53:01+00:00 done x"), ("2026-10-26T16:53:01+00:00", "done x"))
        self.assertEqual(za.split_line("no time here"), ("", "no time here"))


if __name__ == "__main__":
    unittest.main()
