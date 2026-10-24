#!/usr/bin/env python3
"""zingas-os: Val's read-only line to the company website (Zinga's OS). Plain code, no AI.

The website keeps the Salesforce key. Val holds only her own website key (ASSISTANT_API_TOKEN) and asks two
narrow, read-only doors (docs/CONNECTIONS.md):

  zingas-os customer --phone 3175550123      one customer's visits, results and follow-up notes (no prices)
  zingas-os customer --prospect-id a0X...    the same, by Salesforce Prospect ID
  zingas-os numbers [--month 2026-10]        Gerrit's month so far, as on the Numbers tab
  zingas-os appointments [--day tomorrow]    one day of Gerrit's Google Calendar (today by default)
  zingas-os check                            one test call; prints only whether it worked

Used three ways:
  - the pickup program (zingas-quo) adds the customer's record to every draft request,
  - the brief script (zingas_brief_data.py) adds the Monday numbers to the Monday morning brief, and the
    day's appointments to every brief (today's in the morning, tomorrow's in the evening),
  - Val runs `zingas-os customer` in Telegram when Gerrit asks about a customer.

Nothing here can write to Salesforce or the website, or text anyone. Every function returns None (or a short
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


# ---------------------------------------------------------------- command line

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="zingas-os", description="Read-only questions to the company website.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("customer", help="one customer's visits, results and follow-up notes (no prices)")
    c.add_argument("--phone", default="")
    c.add_argument("--prospect-id", default="")
    n = sub.add_parser("numbers", help="Gerrit's numbers for a month (default: this month so far)")
    n.add_argument("--month", default="", help="YYYY-MM")
    a = sub.add_parser("appointments", help="one day of Gerrit's Google Calendar (default: today)")
    a.add_argument("--day", default="", help="YYYY-MM-DD, today or tomorrow")
    sub.add_parser("check", help="one test call; prints only whether it worked")
    args = ap.parse_args(argv)

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
        else:
            site.numbers()
            print("The company website answered. Val's key works.")
    except WebsiteError as e:
        print(f"The company website did not answer ({e}). Nothing was changed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
