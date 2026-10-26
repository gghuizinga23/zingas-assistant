#!/usr/bin/env python3
"""Zinga's Assistant: Val's activity log, the sender on her computer.

Runs on Val's Orgo computer under supervisord (files/zingas-activity.supervisor.conf). About once a minute it
sends quo-bridge (POST /api/val/activity, with the drafts-only code in /root/.hermes/quo-bridge.env):
  - new lines from her programs' logs (/var/log/orgo/zingas-*.log and .err; never Hermes's own chat logs)
  - "list made for <day>: <n> follow-ups" when the follow-up program makes the day's list
  - "brief made" when a morning or evening brief is made
  - every 10 minutes a check-in: which of her programs are running. A program stopped for 30+ minutes
    shows as "stopped 30+ min: <names>", and quo-bridge's watchdog texts Gerrit about it.
quo-bridge keeps it all in its events table; files/val-log.sh shows it on the laptop.

It only reads files and asks supervisord for status. It changes nothing on this computer except its own
small state file. If quo-bridge can't be reached, it keeps its place and sends the lines later.
Python standard library only.
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import time as _time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

HERMES_HOME = os.environ.get("HERMES_HOME", "/root/.hermes")
VAULT = os.environ.get("ZINGAS_VAULT", "/root/Documents/ZingasVault")
LOG_GLOB = os.environ.get("ZINGAS_LOG_GLOB", "/var/log/orgo/zingas-*")
BRIDGE_ENV = os.path.join(HERMES_HOME, "quo-bridge.env")
STATE = os.path.join(HERMES_HOME, "activity-state.json")
PLAN = os.path.join(VAULT, "followups", "state.json")
BRIEF = os.path.join(VAULT, "todo", "last-brief.txt")
SELF = "activity"
LOOP_SLEEP = 60
CHECKIN_EVERY = timedelta(minutes=10)
STOPPED_FOR = timedelta(minutes=30)
READ_MAX = 64 * 1024      # bytes read from one log file in one round
LINES_MAX = 40            # lines sent from one log file in one round; more are counted, not sent
BATCH = 100               # the door's limit for one call
_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?)\s+(.*)$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def say(msg: str) -> None:
    # Only to its own log (which it never reads back: its own files are skipped below).
    print(f"{iso(now_utc())} {msg}", flush=True)


def program_of(path: str) -> str:
    name = os.path.basename(path).rsplit(".", 1)[0]
    name = name[len("zingas-"):] if name.startswith("zingas-") else name
    return re.sub(r"[^a-z0-9-]", "-", name.lower())[:30] or "unknown"


def split_line(raw: str) -> Tuple[str, str]:
    """('2026-10-26T12:53:01+00:00', 'done {...}') from a line that starts with a time; ('', line) if not."""
    m = _STAMP.match(raw)
    return (m.group(1), m.group(2)) if m else ("", raw)


class Sender:
    def __init__(self, url: str, token: str, timeout: float = 15.0):
        if not url.startswith("https://") and not url.startswith("http://127.0.0.1"):
            raise ValueError("QUO_BRIDGE_URL must start with https://")
        self.url, self.token, self.timeout = url.rstrip("/"), token, timeout

    def send(self, events: List[dict], checkin: Optional[str]) -> None:
        body: dict = {"events": events}
        if checkin is not None:
            body["checkin"] = checkin
        req = urllib.request.Request(self.url + "/api/val/activity", method="POST",
                                     data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + self.token,
                                              "Content-Type": "application/json",
                                              "User-Agent": "zingas-activity/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                r.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"quo-bridge: HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"quo-bridge: {type(e).__name__}") from None


def sender_from_env(path: str = BRIDGE_ENV) -> Optional[Sender]:
    vals = {}
    try:
        with open(path) as fh:
            for line in fh:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    vals[k] = v
    except OSError:
        return None
    if not vals.get("QUO_BRIDGE_URL") or not vals.get("VAL_DRAFT_TOKEN"):
        return None
    return Sender(vals["QUO_BRIDGE_URL"], vals["VAL_DRAFT_TOKEN"])


def supervisor_status() -> Dict[str, str]:
    """{'zingas-inbox': 'RUNNING', ...} from supervisorctl; {} if it can't be asked."""
    try:
        out = subprocess.run(["supervisorctl", "status"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    got = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            got[parts[0]] = parts[1]
    return got


class Activity:
    def __init__(self, sender, log_glob: str = LOG_GLOB, state_path: str = STATE, plan_path: str = PLAN,
                 brief_path: str = BRIEF, status=supervisor_status, clock=now_utc):
        self.sender, self.log_glob, self.state_path = sender, log_glob, state_path
        self.plan_path, self.brief_path, self.status, self.clock = plan_path, brief_path, status, clock
        self.st = self._load()

    def _load(self) -> dict:
        try:
            with open(self.state_path) as fh:
                st = json.load(fh)
        except (OSError, ValueError):
            st = {}
        st.setdefault("files", {})
        st.setdefault("stopped_since", {})
        return st

    def save(self) -> None:
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.st, fh)
        os.replace(tmp, self.state_path)

    # ----------------------------------------------------------- log lines
    def _new_lines(self, path: str, first_run: bool) -> Tuple[List[dict], dict]:
        """Lines added to one log since last time, and where to start next time (not saved yet)."""
        try:
            info = os.stat(path)
        except OSError:
            return [], {}
        mark = self.st["files"].get(path)
        if mark is None:
            # A log seen for the first time: on the very first run start at its end (no old history);
            # a log that appears later (a new program) is read from the top.
            start = info.st_size if first_run else 0
        elif mark.get("inode") != info.st_ino or info.st_size < mark.get("offset", 0):
            start = 0                       # the log was rotated: start the new file from the top
        else:
            start = mark.get("offset", 0)
        with open(path, "rb") as fh:
            fh.seek(start)
            chunk = fh.read(READ_MAX)
        cut = chunk.rfind(b"\n") + 1          # whole lines only; a half line waits for the next round
        if cut == 0 and len(chunk) < READ_MAX:
            return [], {"inode": info.st_ino, "offset": start}
        if cut == 0:
            cut = len(chunk)                  # one huge line: send its start, move on
        program = program_of(path)
        err = path.endswith(".err")
        lines = [ln for ln in chunk[:cut].decode("utf-8", "replace").splitlines() if ln.strip()]
        out = []
        lines = [ln for ln in lines if not (program == "heartbeat" and split_line(ln.strip())[1] == "ok")]
        for raw in lines[:LINES_MAX]:
            at, text = split_line(raw.strip())
            out.append({"program": program, "at": at, "line": ("ERR " if err else "") + text})
        if len(lines) > LINES_MAX:
            out.append({"program": program, "at": "", "line": f"(+{len(lines) - LINES_MAX} more lines not sent)"})
        return out, {"inode": info.st_ino, "offset": start + cut}

    def log_lines(self) -> Tuple[List[dict], Dict[str, dict]]:
        first_run = not self.st.get("started")
        events, marks = [], {}
        for path in sorted(glob.glob(self.log_glob)):
            if program_of(path) == SELF or not (path.endswith(".log") or path.endswith(".err")):
                continue
            got, mark = self._new_lines(path, first_run)
            events += got
            if mark:
                marks[path] = mark
        return events, marks

    # ----------------------------------------------------------- the list and the brief
    def milestones(self) -> Tuple[List[dict], dict]:
        events, seen = [], {}
        try:
            with open(self.plan_path) as fh:
                plan = (json.load(fh) or {}).get("plan") or {}
        except (OSError, ValueError):
            plan = {}
        if plan.get("made_at") and plan.get("made_at") != self.st.get("plan_made_at"):
            n = len(plan.get("items") or [])
            events.append({"program": "followups", "at": plan["made_at"],
                           "line": f"list made for {plan.get('day')}: {n} follow-up{'' if n == 1 else 's'}"})
            seen["plan_made_at"] = plan["made_at"]
        try:
            with open(self.brief_path) as fh:
                brief = fh.read().strip()[:40]
        except OSError:
            brief = ""
        if brief and brief != self.st.get("brief_at"):
            if self.st.get("started"):         # not on the very first run: that brief is old news
                events.append({"program": "brief", "at": "", "line": f"brief made (stamp {brief})"})
            seen["brief_at"] = brief
        return events, seen

    # ----------------------------------------------------------- the check-in
    def checkin(self, now: datetime) -> Optional[str]:
        last = self.st.get("last_checkin")
        if last and now - datetime.fromisoformat(last) < CHECKIN_EVERY:
            return None
        status = self.status()
        if not status:
            return "can't read program status (supervisorctl)"
        since = self.st["stopped_since"]
        down = sorted(n for n, s in status.items() if s != "RUNNING")
        for n in list(since):
            if n not in down:
                del since[n]
        for n in down:
            since.setdefault(n, iso(now))
        long_down = [n for n in down if now - datetime.fromisoformat(since[n]) >= STOPPED_FOR]
        if long_down:
            return "stopped 30+ min: " + ", ".join(long_down)
        if down:
            return f"{len(status) - len(down)} of {len(status)} running; just stopped: " + ", ".join(down)
        return f"all {len(status)} running"

    # ----------------------------------------------------------- one round
    def step(self) -> int:
        now = self.clock()
        lines, marks = self.log_lines()
        found, seen = self.milestones()
        events = found + lines
        checkin = self.checkin(now)
        if not events and checkin is None:
            self.st["files"].update(marks)
            self.st["started"] = True
            self.save()
            return 0
        for i in range(0, max(len(events), 1), BATCH):
            last = i + BATCH >= len(events)
            self.sender.send(events[i:i + BATCH], checkin if last else None)   # raises: keep our place
        self.st["files"].update(marks)
        self.st.update(seen)
        self.st["started"] = True
        if checkin is not None:
            self.st["last_checkin"] = iso(now)
        self.save()
        return len(events)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["once"]:        # one round, for a check by hand
        sender = sender_from_env()
        if not sender:
            print("no quo-bridge settings in " + BRIDGE_ENV)
            return 1
        print(f"sent {Activity(sender).step()} lines")
        return 0
    if argv[:1] != ["run"]:
        print("usage: zingas-activity run | once")
        return 2
    say("zingas-activity started; sends Val's activity to quo-bridge every minute")
    act = None
    while True:
        try:
            if act is None:
                sender = sender_from_env()
                if not sender:
                    say("no quo-bridge settings yet; trying again in a minute")
                else:
                    act = Activity(sender)
            if act is not None:
                act.step()
        except Exception as e:      # keep running; never print settings
            say(f"error: {type(e).__name__}: {str(e)[:120]}")
            act = None
        _time.sleep(LOOP_SLEEP)


if __name__ == "__main__":
    sys.exit(main())
