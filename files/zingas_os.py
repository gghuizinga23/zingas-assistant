#!/usr/bin/env python3
"""zingas-os: Val's line to the company website (Zinga's OS). Plain code, no AI.

The website keeps the Salesforce key. Val holds only her own website key (ASSISTANT_API_TOKEN) and asks a few
narrow doors (docs/CONNECTIONS.md):

  zingas-os customer --phone 3175550123      one customer's visits, results and follow-up notes (no prices)
  zingas-os customer --prospect-id a0X...    the same, by Salesforce Prospect ID
  zingas-os numbers [--month 2026-10]        Gerrit's month so far, as on the Numbers tab
  zingas-os appointments [--day tomorrow]    one day of Gerrit's Google Calendar (today by default)
  zingas-os check                            one test call; prints only whether it worked

The Follow-Up sheet (only for reps on the website's VAL_FOLLOWUP_USERS; skill followup-sheet):
  zingas-os followups [--days 120]           her worklist: quoted-but-not-sold visits and open follow-up files
  zingas-os followup-update '<json>'         a note entry, the date, temperature, waiting on, next step
  zingas-os followup-touch '<json>'          logs one text, email, call, visit or note
  zingas-os events [--after ID]              what reps changed on the sheet since she last looked

Used three ways:
  - the pickup program (zingas-quo) adds the customer's record to every draft request,
  - the brief script (zingas_brief_data.py) adds the Monday numbers to the Monday morning brief, and the
    day's appointments to every brief (today's in the morning, tomorrow's in the evening),
  - Val runs `zingas-os customer` in Telegram when Gerrit asks about a customer.

Nothing here can write to Salesforce or text anyone. The only writes are the Follow-Up sheet calls, and the
website decides what they may change: the rep always wins. Every function returns None (or a short
"couldn't reach" line) when the website doesn't answer, so a brief or a draft never fails because of it.
Installed at /usr/local/lib/zingas/zingas_os.py and /usr/local/bin/zingas-os.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Optional

HERMES_HOME = os.environ.get("HERMES_HOME", "/root/.hermes")
OP_ENV = os.path.join(HERMES_HOME, ".op.env")
OP_ITEM = "op://Zingas Assistant/Assistant Secrets/"
TIMEOUT = 25          # seconds; the website asks Salesforce, which can be slow
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def _tz():
    """Indianapolis time, which the calendar and the briefs use."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/Indiana/Indianapolis")
    except Exception:  # no time zone data: the computer's own clock
        return None


class WebsiteError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}" if status else message)
        self.status = status


# ---------------------------------------------------------------- settings

_SECRETS: dict = {}     # read from 1Password once per program run, never written anywhere


def read_secret(name: str) -> str:
    """From the environment (Val's programs get it from 1Password at start), else straight from 1Password.
    Never printed."""
    if os.environ.get(name):
        return os.environ[name].strip()
    if name in _SECRETS:
        return _SECRETS[name]
    value = _op_read(name)
    if value:
        _SECRETS[name] = value
    return value


def _op_read(name: str) -> str:
    token = ""
    try:
        with open(OP_ENV) as fh:
            for line in fh:
                if line.startswith("OP_SERVICE_ACCOUNT_TOKEN="):
                    token = line.split("=", 1)[1].strip()
    except OSError:
        return ""
    if not token:
        return ""
    env = dict(os.environ, OP_SERVICE_ACCOUNT_TOKEN=token)
    try:
        out = subprocess.run(["op", "read", OP_ITEM + name], env=env, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


class Website:
    def __init__(self, url: str, token: str, timeout: float = TIMEOUT):
        self.url, self.token, self.timeout = url.rstrip("/"), token, timeout

    @classmethod
    def from_settings(cls) -> Optional["Website"]:
        url, token = read_secret("ZINGAS_OS_URL"), read_secret("ASSISTANT_API_TOKEN")
        return cls(url, token) if url and token else None

    def get(self, path: str, params: dict) -> dict:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v})
        req = urllib.request.Request(f"{self.url}{path}" + (f"?{query}" if query else ""),
                                     headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raise WebsiteError(e.code, e.read().decode("utf-8", "replace")[:200].strip() or e.reason) from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise WebsiteError(0, f"no answer ({type(e).__name__})") from None

    def post(self, path: str, body: dict, ok_statuses=(200,)) -> tuple:
        """(status, answer). A status in ok_statuses comes back as is (with its JSON answer); others raise."""
        req = urllib.request.Request(f"{self.url}{path}", data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            if e.code in ok_statuses:
                try:
                    return e.code, json.loads(text or "{}")
                except ValueError:
                    pass
            raise WebsiteError(e.code, text[:200].strip() or e.reason) from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise WebsiteError(0, f"no answer ({type(e).__name__})") from None

    def followups(self, rep: str = "", days: int = 0) -> dict:
        return self.get("/api/assistant/followups", {"rep": rep, "days": days or ""})

    def followup_update(self, body: dict) -> tuple:
        return self.post("/api/assistant/followups/update", body, ok_statuses=(200, 409))

    def followup_touch(self, body: dict) -> tuple:
        return self.post("/api/assistant/followups/touch", body)

    def events(self, after: int = 0, types: str = "") -> dict:
        return self.get("/api/assistant/events", {"after": after or "", "types": types})

    def customer(self, phone: str = "", prospect_id: str = "") -> dict:
        return self.get("/api/assistant/customer", {"phone": digits(phone), "prospectId": prospect_id.strip()})

    def numbers(self, month: str = "", today: str = "") -> dict:
        return self.get("/api/assistant/numbers", {"month": month, "today": today})

    def appointments(self, day: str = "") -> dict:
        return self.get("/api/assistant/appointments", {"day": day})


def digits(phone: str) -> str:
    """The last 10 digits of a US number, or "" when it has fewer."""
    d = re.sub(r"\D", "", phone or "")
    return d[-10:] if len(d) >= 10 else ""


# ---------------------------------------------------------------- customer

def lookup_phone(phone: str, site: Optional[Website] = None) -> Optional[dict]:
    """The website's answer for this number, or None when it can't be asked (no settings, no answer)."""
    if not digits(phone):
        return None
    site = site or Website.from_settings()
    if site is None:
        return None
    try:
        return site.customer(phone=phone)
    except WebsiteError:
        return None


def matched(result: Optional[dict]) -> Optional[dict]:
    """The one customer the website matched, or None (no match, several, or no answer)."""
    return (result or {}).get("customer") or None


def customer_block(result: Optional[dict]) -> str:
    """The website's record as plain lines for Val. Never a price: the website sends none."""
    if result is None:
        return "The company website did not answer, so there is no Salesforce record this time."
    c = matched(result)
    if c is None:
        cands = result.get("candidates") or []
        if not cands:
            return "No Salesforce customer of Gerrit's has this number (last 18 months)."
        lines = [f"This number belongs to {len(cands)} Salesforce customers. Gerrit must say which one:"]
        lines += [f"- {k.get('name')}, {k.get('city')}, last visit {k.get('lastVisit')} "
                  f"(Prospect ID {k.get('prospectId')})" for k in cands[:5]]
        return "\n".join(lines)
    lines = [f"Salesforce customer: {c.get('name')}, {c.get('city')}. Prospect ID {c.get('prospectId')}."]
    for v in (c.get("visits") or [])[:6]:
        what = " ".join(x for x in (v.get("result"), v.get("resultDetail")) if x) or "no result yet"
        line = f"- {v.get('date')}: {v.get('product') or 'visit'} with {v.get('rep')}: {what}."
        if v.get("followUpDate"):
            line += f" Follow-up date {v['followUpDate']}."
        if v.get("note"):
            line += f" Follow-up note: {' '.join(str(v['note']).split())[:300]}"
        lines.append(line)
    for o in (c.get("blockedOrders") or [])[:3]:
        lines.append(f"- Order {o.get('sale')} is held: {o.get('blocker')} ({o.get('status')}).")
    return "\n".join(lines)


# ---------------------------------------------------------------- numbers

def money(n) -> str:
    return f"${n:,.0f}" if isinstance(n, (int, float)) else "n/a"


def pct(n) -> str:
    return f"{n * 100:.0f}%" if isinstance(n, (int, float)) else "n/a"


def numbers_lines(d: dict) -> list:
    """The month's numbers as fixed lines, worked out here so Val copies them exactly."""
    y, m = (int(x) for x in d["month"].split("-"))
    as_of = date.fromisoformat(d["asOf"])
    head = (f"📊 {MONTHS[m - 1]} so far (to {as_of:%b} {as_of.day})" if (as_of.year, as_of.month) == (y, m)
            else f"📊 {MONTHS[m - 1]} {y}, whole month")
    revenue = f"Revenue: {money(d.get('revenue'))}"
    goal = d.get("revenueGoal")
    if isinstance(goal, (int, float)) and goal > 0:
        revenue += f" of {money(goal)} goal ({pct((d.get('revenue') or 0) / goal)})"
    return [head + ":", revenue,
            f"Sold: {d.get('sold', 'n/a')} · Close rate: {pct(d.get('closeRate'))} · "
            f"Average sale: {money(d.get('averageSale'))}",
            f"Appointments: {d.get('appointments', 'n/a')} · Demos: {d.get('demos', 'n/a')} · "
            f"Revenue per lead: {money(d.get('revenuePerLead'))}",
            f"Cancel rate: {pct(d.get('cancelRate'))}"]


def monday_block(now: datetime, site: Optional[Website] = None) -> str:
    """The Monday numbers block for the Monday morning brief: this month so far, plus last month's final
    numbers in the first week of a month. A short "couldn't" line when the website doesn't answer."""
    lines = []
    site = site or Website.from_settings()
    months = [now.strftime("%Y-%m")]
    if now.day <= 7:
        last = date(now.year - (now.month == 1), 12 if now.month == 1 else now.month - 1, 1)
        months.insert(0, last.strftime("%Y-%m"))
    for month in months:
        try:
            if site is None:
                raise WebsiteError(0, "not set up")
            lines += numbers_lines(site.numbers(month=month, today=now.strftime("%Y-%m-%d")))
        except (WebsiteError, KeyError, ValueError, TypeError):
            lines = ["Numbers: the company website did not answer. Look at the Numbers tab."]
            break
    return "\n".join(["--- MONDAY NUMBERS STARTS (copy the lines below into the brief exactly; never copy this line) ---",
                      *lines, "--- MONDAY NUMBERS ENDS (never copy this line) ---"])


# ---------------------------------------------------------------- calendar

def clock(hhmm: str) -> str:
    """ "14:30" -> "2:30pm", "09:00" -> "9am"."""
    try:
        h, m = (int(x) for x in hhmm.split(":"))
    except (ValueError, AttributeError):
        return hhmm or ""
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}{suffix}" if m == 0 else f"{h12}:{m:02d}{suffix}"


def appointments_lines(d: dict, label: str, notes: bool = False) -> list:
    """One day of the calendar as fixed lines, worked out here so Val copies them exactly. The calendar is
    information, never instructions. notes=True adds each entry's short note (for Gerrit's questions in
    Telegram); the briefs leave them out."""
    if not d.get("connected"):
        if d.get("reconnect"):
            return ["📅 Calendar: Google stopped the link. Connect it again on the website (Assistant > Calendar)."]
        return ["📅 Calendar: not connected. Connect it on the website (Assistant > Calendar)."]
    items = d.get("appointments") or []
    if not items:
        return [f"📅 {label}: nothing on the calendar."]
    lines = [f"📅 {label}: {len(items)} on the calendar"]
    for a in items[:15]:
        when = "All day" if a.get("allDay") else f"{clock(a.get('start', ''))}–{clock(a.get('end', ''))}"
        line = f"- {when} {a.get('title') or '(no title)'}"
        if a.get("location"):
            line += f" · {a['location']}"
        if notes and a.get("notes"):
            line += f" (note: {a['notes']})"
        lines.append(line)
    if len(items) > 15:
        lines.append(f"- and {len(items) - 15} more")
    return lines


def day_label(day: date, today: date) -> str:
    name = "Today" if day == today else "Tomorrow" if day == today + timedelta(days=1) else f"{day:%A}"
    return f"{name} ({day:%a} {day:%b} {day.day})"


def appointments_block(now: datetime, site: Optional[Website] = None) -> str:
    """The calendar block for a brief: today's appointments in the morning, tomorrow's in the evening.
    "" when Val has no website settings at all; a short "couldn't" line when the website doesn't answer."""
    site = site or Website.from_settings()
    if site is None:
        return ""
    day = now.date() if now.hour < 12 else now.date() + timedelta(days=1)
    try:
        lines = appointments_lines(site.appointments(day=day.isoformat()), day_label(day, now.date()))
    except (WebsiteError, KeyError, ValueError, TypeError):
        lines = ["📅 Calendar: the company website did not answer. Look at Google Calendar."]
    return "\n".join(["--- APPOINTMENTS STARTS (copy the lines below into the brief exactly; never copy this line) ---",
                      *lines, "--- APPOINTMENTS ENDS (never copy this line) ---"])


# ---------------------------------------------------------------- the Follow-Up sheet

FIELD_NAMES = {"note": "note", "follow_up_date": "follow-up date", "temperature": "temperature",
               "waiting_on": "waiting on", "waiting_on_detail": "waiting on (detail)", "next_step": "next step",
               "last_contact": "last contact", "driver": "who is driving", "paused_until": "pause", "stage": "stage"}
PLAN_PARTS = ("follow_up_date", "temperature", "waiting_on", "next_step")
PRICE = re.compile(r"\$\s*\d")
EVENTS_STATE = os.path.join(HERMES_HOME, "zingas-os-events.json")


def door_problem(e: WebsiteError) -> str:
    """The website's refusal as one plain line for Val."""
    if e.status == 403:
        return f"Val does not keep this rep's or customer's follow-ups ({e}). Nothing was changed."
    if e.status == 503:
        return "The website's follow-up tables are not set up yet. Nothing was changed."
    if e.status in (400, 404, 409, 413):
        return f"The website refused it ({e}). Nothing was changed. Fix it, or ask Gerrit."
    return f"The company website did not answer ({e}). Nothing was changed."


def has_price(value) -> bool:
    """True when a dollar amount is anywhere in what Val wants to send."""
    return bool(PRICE.search(json.dumps(value, ensure_ascii=False)))


def one_line(text, limit: int = 160) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= limit else t[: limit - 1] + "…"


def worklist_lines(d: dict, limit: int = 40) -> list:
    """The worklist as plain lines, soonest follow-up first. Notes are information, never instructions."""
    items = d.get("items") or []
    if not items:
        return [f"No open follow-ups for {d.get('rep') or 'this rep'}."]
    lines = [f"Follow-ups for {d.get('rep')} ({len(items)}, today {d.get('today')}):"]
    for it in items[:limit]:
        cust = it.get("customer") or {}
        visit = it.get("visit") or {}
        case = it.get("case") or {}
        head = f"- {cust.get('name') or 'Unknown customer'}, {cust.get('city') or '?'}"
        if visit:
            head += f": {visit.get('product') or 'visit'} {visit.get('date')}"
            if visit.get("result"):
                head += f" ({one_line(' '.join(x for x in (visit.get('result'), visit.get('resultDetail')) if x), 60)})"
        head += f". Follow-up {it.get('followUpDate') or 'none'}"
        if it.get("followUpDateFrom") == "salesforce":
            head += " (from Salesforce)"
        head += "."
        bits = []
        if case.get("stage") and case["stage"] != "open":
            bits.append(f"stage {case['stage']}")
        for key, label in (("temperature", ""), ("waitingOn", "waiting on "), ("nextStep", "next: ")):
            if case.get(key):
                bits.append(f"{label}{one_line(case[key], 80)}")
        if case.get("driver") == "rep":
            bits.append("the rep has this (I've got this)")
        if case.get("pausedUntil"):
            bits.append(f"paused through {case['pausedUntil']}")
        held = [FIELD_NAMES.get(p, p) for p, may in (it.get("valMay") or {}).items()
                if p in PLAN_PARTS and not (may or {}).get("ok")]
        if held and case.get("driver") != "rep" and not case.get("pausedUntil"):
            bits.append("rep holds " + ", ".join(held))
        if bits:
            head += " " + "; ".join(bits) + "."
        lines.append(head)
        note = (it.get("notes") or {}).get("followup")
        if note:
            lines.append(f"  Note{' (Val)' if (it.get('notes') or {}).get('followupBy') == 'val' else ''}: "
                         f"{one_line(note.splitlines()[0], 160)}")
        lines.append(f"  Appointment {it.get('appointmentId')}, Prospect ID {it.get('prospectId')}.")
    if len(items) > limit:
        lines.append(f"- and {len(items) - limit} more")
    return lines


def update_lines(status: int, d: dict) -> list:
    applied = [FIELD_NAMES.get(f, f) for f in d.get("applied") or []]
    lines = [f"Changed on the sheet: {', '.join(applied)}." if applied else "Nothing was changed on the sheet."]
    for r in d.get("refused") or []:
        lines.append(f"Not changed, {FIELD_NAMES.get(r.get('field'), r.get('field'))}: {r.get('reason')} "
                     "Do not try this again; the rep's choice wins.")
    if applied and d.get("followUpDate"):
        lines.append(f"Follow-up date now {d['followUpDate']}.")
    return lines


def event_line(e: dict) -> str:
    data = e.get("data") or {}
    kind = e.get("type")
    if kind == "followup_rep_changed":
        what = ", ".join(FIELD_NAMES.get(f, f) if f != "followup_note" else "follow-up note" for f in data.get("fields") or [])
        verb = "undid Val's" if data.get("action") == "undo" else "changed the"
        return (f"#{e.get('id')} {e.get('created_at', '')[:16]}: {data.get('by')} {verb} {what or 'follow-up'} on "
                f"appointment {data.get('appointmentId')} (Prospect ID {e.get('prospect_id')}). Read the worklist "
                "again before doing anything for this customer.")
    return f"#{e.get('id')} {e.get('created_at', '')[:16]}: {kind} (Prospect ID {e.get('prospect_id')})."


def load_place(path: str = "") -> int:
    try:
        with open(path or EVENTS_STATE) as fh:
            return int(json.load(fh).get("last") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def save_place(last: int, path: str = "") -> None:
    path = path or EVENTS_STATE
    tmp = path + ".new"
    with open(tmp, "w") as fh:
        json.dump({"last": int(last), "at": datetime.now(_tz()).isoformat(timespec="seconds")}, fh)
    os.replace(tmp, path)


def parse_body(raw: str) -> Optional[dict]:
    try:
        body = json.loads(raw)
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


# ---------------------------------------------------------------- command line

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="zingas-os", description="Val's questions to the company website.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("customer", help="one customer's visits, results and follow-up notes (no prices)")
    c.add_argument("--phone", default="")
    c.add_argument("--prospect-id", default="")
    n = sub.add_parser("numbers", help="Gerrit's numbers for a month (default: this month so far)")
    n.add_argument("--month", default="", help="YYYY-MM")
    a = sub.add_parser("appointments", help="one day of Gerrit's Google Calendar (default: today)")
    a.add_argument("--day", default="", help="YYYY-MM-DD, today or tomorrow")
    sub.add_parser("check", help="one test call; prints only whether it worked")
    f = sub.add_parser("followups", help="the Follow-Up worklist (default: Gerrit, last 120 days)")
    f.add_argument("--rep", default="", help="the rep's email (default: the first rep Val works for)")
    f.add_argument("--days", type=int, default=0, help="1 to 400 (default 120)")
    f.add_argument("--json", action="store_true", help="the website's whole answer")
    u = sub.add_parser("followup-update", help="change one customer's follow-up (JSON, see skill followup-sheet)")
    u.add_argument("body", help="the JSON body; '-' reads it from standard input")
    t = sub.add_parser("followup-touch", help="log one touch (JSON, see skill followup-sheet)")
    t.add_argument("body", help="the JSON body; '-' reads it from standard input")
    e = sub.add_parser("events", help="what changed on the sheet since Val last looked (then remembers the place)")
    e.add_argument("--after", type=int, default=None, help="start after this event id (does not move the place)")
    e.add_argument("--types", default="", help="comma-separated event names")
    args = ap.parse_args(argv)

    if args.cmd in ("followup-update", "followup-touch"):
        body = parse_body(sys.stdin.read() if args.body == "-" else args.body)
        if body is None or not body.get("appointmentId"):
            print("Give one JSON object with at least appointmentId. Nothing was changed.")
            return 2
        if has_price(body):
            print("That has a dollar amount in it. Never send a price to the sheet. Nothing was changed.")
            return 2

    site = Website.from_settings()
    if site is None:
        print("The website key or address is not set up (1Password: ASSISTANT_API_TOKEN, ZINGAS_OS_URL).")
        return 1
    try:
        if args.cmd == "customer":
            if not digits(args.phone) and not args.prospect_id.strip():
                print("Give a 10-digit --phone or a --prospect-id.")
                return 2
            print(customer_block(site.customer(phone=args.phone, prospect_id=args.prospect_id)))
        elif args.cmd == "appointments":
            today = datetime.now(_tz()).date()
            want = args.day.strip().lower()
            try:
                day = (today if want in ("", "today") else today + timedelta(days=1) if want == "tomorrow"
                       else date.fromisoformat(want))
            except ValueError:
                print("Give --day as YYYY-MM-DD, today or tomorrow.")
                return 2
            print("\n".join(appointments_lines(site.appointments(day=day.isoformat()), day_label(day, today),
                                               notes=True)))
        elif args.cmd == "numbers":
            print("\n".join(numbers_lines(site.numbers(month=args.month))))
        elif args.cmd == "followups":
            if args.days and not 1 <= args.days <= 400:
                print("Give --days from 1 to 400.")
                return 2
            d = site.followups(rep=args.rep, days=args.days)
            print(json.dumps(d, indent=1, ensure_ascii=False) if args.json else "\n".join(worklist_lines(d)))
        elif args.cmd == "followup-update":
            status, d = site.followup_update(body)
            print("\n".join(update_lines(status, d)))
            return 0 if status == 200 else 3
        elif args.cmd == "followup-touch":
            site.followup_touch(body)
            print("Touch logged.")
        elif args.cmd == "events":
            after = load_place() if args.after is None else args.after
            d = site.events(after=after, types=args.types)
            lines = [event_line(x) for x in d.get("events") or []]
            print("\n".join(lines) if lines else "Nothing new on the sheet.")
            if args.after is None and isinstance(d.get("last"), int) and d["last"] > after:
                save_place(d["last"])
        else:
            site.numbers()
            print("The company website answered. Val's key works.")
    except WebsiteError as e:
        if args.cmd.startswith("followup") or args.cmd == "events":
            print(door_problem(e))
        else:
            print(f"The company website did not answer ({e}). Nothing was changed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
