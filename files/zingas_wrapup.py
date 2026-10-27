#!/usr/bin/env python3
"""End-of-day wrap-up (plan F3, as Gerrit rethought it). Plain code, no AI of its own.

Gerrit doesn't want Val asking "Sold, Quoted or Lost?" and wants no new tasks on his plate. So Val reads the day's
visits and their results herself, from the company website (Salesforce, through GET /api/assistant/day), and the
evening brief says, per visit, what happened and what Val does next:

  Sold            the after-install texts start when the job shows under the Gmail label Completed (F4)
  Demoed, Not Sold  the quote follow-ups: on (next touch and day), or "no estimate email yet" (F0 starts on it)
  Not Demoed / No Show / Canceled   said once, nothing to do
  no result yet   said, and checked again each evening for 3 days; then one "still no result" line

It also says when a visit was recorded on Plaud (its note to paste is in the Visits block). Each visit shows once
when it is settled. Customer data stays in the vault (wrapup/state.json). The brief must never fail because of it.

  zingas-wrapup preview [--day YYYY-MM-DD]   the block for a day; changes nothing
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional

sys.path.insert(0, "/usr/local/lib/zingas")
sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))
import zingas_todo as zt  # noqa: E402

TZ = zt.TZ
VAULT = os.environ.get("ZINGAS_VAULT", "/root/Documents/ZingasVault")
REP = os.environ.get("ZINGAS_SHEET_REP", "gerrithuizinga@zingashome.com")
RECHECK_DAYS = 3          # a visit with no result is checked again for this many evenings
WORK_DAYS = frozenset({0, 1, 2, 3, 4, 5})

SOLD = "Sold"
QUOTED = "Demoed, Not Sold"
NOTHING = ("Not Demoed", "No Show", "Canceled")


def state_path(vault: str = VAULT) -> str:
    return os.path.join(vault, "wrapup", "state.json")


def load_state(vault: str = VAULT) -> dict:
    try:
        with open(state_path(vault)) as fh:
            st = json.load(fh)
        return st if isinstance(st, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(st: dict, vault: str = VAULT) -> None:
    d = os.path.dirname(state_path(vault))
    os.makedirs(d, mode=0o700, exist_ok=True)
    tmp = state_path(vault) + ".new"
    with open(tmp, "w") as fh:
        json.dump(st, fh, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, state_path(vault))


def digits10(phone) -> str:
    d = "".join(ch for ch in str(phone or "") if ch.isdigit())
    return d[-10:] if len(d) >= 10 else ""


# ---------------------------------------------------------------- what Val already knows

def f0_customers(vault: str = VAULT) -> List[dict]:
    """The quote follow-up customers (F0), from its own state file."""
    try:
        with open(os.path.join(vault, "followups", "state.json")) as fh:
            return list((json.load(fh).get("customers") or {}).values())
    except (OSError, ValueError, AttributeError):
        return []


def f0_for(visit: dict, customers: List[dict]) -> Optional[dict]:
    cust = visit.get("customer") or {}
    email = str(cust.get("email") or "").lower().strip()
    phone = digits10(cust.get("phone"))
    for c in customers:
        if email and str(c.get("email") or "").lower() == email:
            return c
        if phone and digits10(c.get("phone")) == phone:
            return c
    return None


def next_touch(c: dict) -> str:
    """ "the 48-hour text on Wed" or ""."""
    planned = sorted((t.get("due") or "", label) for label, t in (c.get("touches") or {}).items()
                     if t.get("state") == "planned" and t.get("due"))
    if not planned:
        return ""
    due, label = planned[0]
    try:
        day = datetime.fromisoformat(due).astimezone(TZ).strftime("%a %b %-d")
    except ValueError:
        return f"the {label} touch"
    return f"the {label} touch on {day}"


def recorded(visit: dict, day: date, vault: str = VAULT) -> bool:
    """A Plaud recording of this visit is in the customer's file."""
    pid = str(visit.get("prospectId") or "")
    if not pid or not pid.replace("_", "").replace("-", "").isalnum():
        return False
    folder = os.path.join(vault, "visits", pid)
    try:
        return any(n.startswith(day.isoformat()) for n in os.listdir(folder))
    except OSError:
        return False


# ---------------------------------------------------------------- the lines

def who(visit: dict) -> str:
    cust = visit.get("customer") or {}
    name = cust.get("name") or "A customer"
    city = cust.get("city") or ""
    return f"{name}{', ' + city if city else ''}"


def clock(hhmm: str) -> str:
    try:
        h, m = (int(x) for x in str(hhmm).split(":")[:2])
    except (ValueError, TypeError):
        return ""
    return f"{h % 12 or 12}{'' if m == 0 else f':{m:02d}'}{'am' if h < 12 else 'pm'}"


def visit_line(visit: dict, day: date, customers: List[dict], vault: str = VAULT) -> str:
    """One line per visit: who, what happened, what Val does. Never a price (the website sends none)."""
    result = str(visit.get("result") or "").strip()
    product = str(visit.get("product") or "").strip()
    head = " ".join(x for x in (clock(visit.get("time") or ""), who(visit)) if x)
    head += f" ({product})" if product else ""
    tail = " Recorded on Plaud: the note to paste is in Visits." if recorded(visit, day, vault) else ""
    if result == SOLD:
        return (f"- {head}: Sold. After the install, Val starts the after-install texts when the job is under "
                f"the Completed label.{tail}")
    if result == QUOTED:
        c = f0_for(visit, customers)
        if not c:
            return (f"- {head}: Quoted. Val has not seen the estimate email yet. The follow-ups start by "
                    f"themselves when you send it.{tail}")
        if c.get("status") == "active":
            nxt = next_touch(c)
            return f"- {head}: Quoted. Follow-ups are on" + (f": {nxt}." if nxt else ".") + tail
        if c.get("status") == "paused":
            return f"- {head}: Quoted. Follow-ups wait: they wrote back, so Val waits for 3 quiet days.{tail}"
        why = c.get("why") or c.get("status") or "stopped"
        return f"- {head}: Quoted. Follow-ups are off ({why}).{tail}"
    if result in NOTHING:
        detail = str(visit.get("resultDetail") or "").strip()
        return f"- {head}: {result}{' (' + detail + ')' if detail else ''}. Nothing for Val to do.{tail}"
    if result:
        return f"- {head}: {result}.{tail}"
    return f"- {head}: no result in Salesforce yet. Val looks again tomorrow evening.{tail}"


def days_to_cover(today: date) -> List[date]:
    """Today, and on Monday also Saturday (the evening brief runs Monday to Friday)."""
    out = [today]
    if today.weekday() == 0:
        out.insert(0, today - timedelta(days=2))
    return out


def build(now: datetime, read_day: Callable[[date], Optional[dict]], vault: str = VAULT,
          st: Optional[dict] = None) -> List[str]:
    """The block's lines (without the markers). st is changed in place: what was shown, what is still open."""
    st = st if st is not None else {}
    today = now.astimezone(TZ).date()
    customers = f0_customers(vault)
    shown: Dict[str, str] = st.setdefault("shown", {})          # appointmentId -> the day it was settled
    waiting: Dict[str, dict] = st.setdefault("waiting", {})     # appointmentId -> {day, name, tries}
    out: List[str] = []
    for day in days_to_cover(today):
        answer = read_day(day)
        if answer is None:
            out.append(f"Val could not read {day:%A}'s visits from the company website. She tries again "
                       "tomorrow evening.")
            continue
        visits = [v for v in answer.get("visits") or [] if v.get("appointmentId")]
        if not visits:
            continue
        label = "Today" if day == today else f"{day:%A}"
        rows = []
        for v in visits:
            aid = str(v["appointmentId"])
            if aid in shown:
                continue
            rows.append(visit_line(v, day, customers, vault))
            if v.get("result"):
                shown[aid] = day.isoformat()
                waiting.pop(aid, None)
            else:
                waiting.setdefault(aid, {"day": day.isoformat(), "name": who(v), "tries": 0})
        if rows:
            out.append(f"{label}'s visits ({len(visits)}):")
            out += rows
    # visits from before with no result yet
    later = []
    for aid, w in sorted(waiting.items(), key=lambda kv: kv[1].get("day") or ""):
        if w.get("day") in {d.isoformat() for d in days_to_cover(today)}:
            continue
        try:
            day = date.fromisoformat(w["day"])
        except (KeyError, ValueError):
            waiting.pop(aid, None)
            continue
        answer = read_day(day)
        v = next((x for x in (answer or {}).get("visits") or [] if str(x.get("appointmentId")) == aid), None)
        if v and v.get("result"):
            later.append(visit_line(v, day, customers, vault).replace("- ", f"- {day:%a}: ", 1))
            shown[aid] = day.isoformat()
            waiting.pop(aid, None)
            continue
        w["tries"] = int(w.get("tries") or 0) + 1
        if w["tries"] >= RECHECK_DAYS or (today - day).days > 7:
            later.append(f"- {day:%a}: {w.get('name')}: still no result in Salesforce. Val stops checking. "
                         "Enter the result so the follow-ups know what to do.")
            shown[aid] = day.isoformat()
            waiting.pop(aid, None)
    if later:
        out.append("Earlier visits:")
        out += later
    # keep the state small
    cutoff = (today - timedelta(days=45)).isoformat()
    for aid in [a for a, d in shown.items() if d < cutoff]:
        shown.pop(aid)
    return out


def website_day(rep: str = REP) -> Callable[[date], Optional[dict]]:
    """read_day for the real website; None for a day when it can't be asked."""
    import zingas_os as zo
    site = zo.Website.from_settings()

    def read(day: date) -> Optional[dict]:
        if site is None:
            return None
        try:
            return site.get("/api/assistant/day", {"day": day.isoformat(), "rep": rep})
        except zo.WebsiteError:
            return None
    return read


def brief_block(now: datetime, vault: str = VAULT, read_day: Optional[Callable[[date], Optional[dict]]] = None,
                save: bool = True) -> str:
    """The WRAP-UP block for the evening brief, or "" (mornings, no settings, nothing to say)."""
    local = now.astimezone(TZ)
    if local.hour < 12:
        return ""
    try:
        read_day = read_day or website_day()
    except Exception:
        return ""
    st = load_state(vault)
    lines = build(local, read_day, vault, st)
    if save:
        save_state(st, vault)
    if not lines:
        return ""
    return "\n".join(["--- WRAP-UP STARTS (put these lines in the brief as written; never copy this line) ---",
                      *lines, "--- WRAP-UP ENDS (never copy this line) ---"])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="zingas-wrapup", description="End-of-day wrap-up (F3).")
    sub = p.add_subparsers(dest="cmd", required=True)
    pv = sub.add_parser("preview")
    pv.add_argument("--day", default="")
    a = p.parse_args(argv)
    now = datetime.now(TZ)
    if a.day:
        d = date.fromisoformat(a.day)
        now = datetime(d.year, d.month, d.day, 19, 0, tzinfo=TZ)
    print(brief_block(now, save=False) or "Nothing to wrap up for that day.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
