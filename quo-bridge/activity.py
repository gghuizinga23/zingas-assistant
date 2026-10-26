"""Val's activity log and the watchdog, the quo-bridge side.

Val's computer runs one small program (files/zingas_activity.py) that sends here, about once a minute:
  - new lines from her programs' logs (follow-ups, backup, inbox, money, text pickup, Plaud ...)
  - "list made for <day>" when the day's follow-up list is made, "brief made" when a brief is made
  - every 10 minutes a check-in that says which of her programs are running
Each line becomes one row in the events table (kind "val:<program>"), next to quo-bridge's own rows, so
one place answers "what did Val do today?" (files/val-log.sh reads it). The door needs Val's code.

The watchdog runs in the every-minute timer here on Vercel, away from Val's computer, so it still works
when her computer is off. It texts Gerrit's cell (GERRIT_CELL) from the Quo number:
  - no check-in for 30 minutes: "Val is down", then "Val is back" when check-ins start again
  - a program stopped for 30+ minutes (once a day per program list)
  - on a weekday, no follow-up list by 8:10 AM (once a day)
Texts wait for 7 AM to 10 PM Indianapolis. Each text sent is a "watchdog" row in events, which is also
how it knows what it already said. Before the first check-in ever arrives it says nothing.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from clients import QuoError
from store import parse_time, utc_iso

Response = Tuple[int, dict]

TZ = ZoneInfo("America/Indiana/Indianapolis")
MAX_EVENTS = 100            # lines in one call
MAX_LINE = 300              # characters kept from one line
PROGRAM_RE = re.compile(r"^[a-z0-9-]{1,30}$")
DOWN_AFTER = timedelta(minutes=30)
LIST_BY = time(8, 10)
SETTLE = timedelta(minutes=15)   # after Val comes back, give her this long to catch up before the list check
AWAKE_FROM, AWAKE_TO = 7, 22     # hours, Indianapolis
STOPPED = "stopped 30+ min:"     # how a check-in names programs that stay stopped


def _clean(s, limit: int = MAX_LINE) -> str:
    s = "".join(ch if ch.isprintable() else " " for ch in str(s or "")).strip()
    return s[:limit]


def receive(store, payload: dict, now: datetime) -> Response:
    """POST /api/val/activity: {"checkin": "...", "events": [{"program", "at", "line"}, ...]}."""
    events = payload.get("events") or []
    checkin = payload.get("checkin")
    if not isinstance(events, list) or (checkin is not None and not isinstance(checkin, str)):
        return 400, {"error": "send {'checkin': '...', 'events': [{'program', 'at', 'line'}]}"}
    if len(events) > MAX_EVENTS:
        return 400, {"error": f"at most {MAX_EVENTS} lines at a time"}
    rows = []
    for n, ev in enumerate(events):
        if not isinstance(ev, dict):
            return 400, {"error": f"line {n} is not an object"}
        program = str(ev.get("program") or "")
        if not PROGRAM_RE.match(program):
            return 400, {"error": f"line {n}: 'program' must be a short name like 'followups'"}
        line = _clean(ev.get("line"))
        if not line:
            continue
        at = parse_time(str(ev.get("at") or "")) if ev.get("at") else None
        if not at or at > now + timedelta(minutes=5) or at < now - timedelta(days=2):
            at = now
        rows.append({"at": utc_iso(at), "kind": "val:" + program, "draft_id": None, "detail": line})
    if checkin is not None:
        rows.append({"at": utc_iso(now), "kind": "val:checkin", "draft_id": None,
                     "detail": _clean(checkin) or "checked in"})
    if rows:
        store.log_many(rows)
    return 200, {"saved": len(rows)}


def _clock(dt: datetime, now: datetime) -> str:
    local, today = dt.astimezone(TZ), now.astimezone(TZ).date()
    out = local.strftime("%-I:%M %p")
    return out if local.date() == today else local.strftime("%a ") + out


def _text(store, quo, cell: str, now: datetime, key: str, message: str) -> str:
    try:
        quo.send_text(cell, message)
    except QuoError as e:
        store.log("watchdog_failed", None, f"{key}: {e}"[:300], utc_iso(now))
        return ""
    store.log("watchdog", None, key, utc_iso(now))
    return key


def watch(store, quo, cell: str, now: datetime) -> str:
    """One look, from the every-minute timer. Returns what it texted ("" for nothing)."""
    if not cell:
        return ""
    last = store.last_event("val:checkin")
    if not last:
        return ""                                   # Val's side isn't installed yet
    seen = parse_time(last["at"])
    local = now.astimezone(TZ)
    awake = AWAKE_FROM <= local.hour < AWAKE_TO
    down = store.last_event("watchdog", "down")
    back = store.last_event("watchdog", "back")
    alerted = bool(down) and (not back or parse_time(back["at"]) < parse_time(down["at"]))

    if now - seen > DOWN_AFTER:
        if alerted or not awake:
            return ""
        return _text(store, quo, cell, now, "down",
                     f"Val watchdog: Val hasn't checked in since {_clock(seen, now)}. Her computer may be off "
                     f"(on 10/25 it was Orgo credits running out). Tell Claude.")
    if alerted:
        if not awake:
            return ""
        return _text(store, quo, cell, now, "back", f"Val watchdog: Val is back. She checked in at {_clock(seen, now)}.")
    if not awake:
        return ""

    today = local.date().isoformat()
    detail = last.get("detail") or ""
    if detail.startswith(STOPPED):
        names = detail[len(STOPPED):].strip()
        key = f"stopped {today}: {names}"
        if not store.last_event("watchdog", key):
            return _text(store, quo, cell, now, key,
                         f"Val watchdog: on Val's computer, {names} stopped over 30 minutes ago. Tell Claude.")

    settled = not back or now - parse_time(back["at"]) >= SETTLE
    if local.weekday() < 5 and local.time() >= LIST_BY and settled:
        if not store.last_event("val:followups", f"list made for {today}") \
                and not store.last_event("watchdog", f"no list {today}"):
            return _text(store, quo, cell, now, f"no list {today}",
                         "Val watchdog: Val hasn't made today's follow-up list (it's due at 7:40 AM). Tell Claude.")
    return ""
