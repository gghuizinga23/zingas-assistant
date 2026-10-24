#!/usr/bin/env python3
"""zingas-money: Val's hourly cost count. Plain code, no AI.

Runs on Val's computer under supervisord. About once an hour it counts what Val costs this month and posts
one count to the company website's door, POST {website}/api/assistant/cost, with Val's own website key
(ASSISTANT_API_TOKEN). The website shows it on Assistant > Cost. The JSON shape is in docs/CONNECTIONS.md,
"Val's cost count"; check_count() below checks a count the same way the website does, so a count is never
refused there.

Where the numbers come from (docs/PLAN.md, "Money: costs and ROI"):
  - AI: Hermes keeps the tokens of every call in ~/.hermes/state.db (table session_model_usage: the gateway,
    the briefs and every oneshot call). Tokens x the public prices in money_prices.json. Nous Plus is $20 a
    month with $22 of use included, so the Nous line is the plan plus any use over $22.
  - Fixed plans: money/subscriptions.json in the vault. Val fills it from receipts. A receipt this month
    makes the line "receipt"; without one the plan price stands in as an "estimate".
  - Backblaze: the size of what the nightly backup has stored (backup-state.json). Free under 10 GB.
  - Credits: how much Nous use Val has left (this month's included use, plus prepaid credits from
    money/credits.json when Val has written it) and how many days that lasts at the last 7 days' pace.
  - Results: follow-ups sent this month (F0's own list). quo-bridge sends the texts count itself.

Never sent: customers, quotes, sales, keys. Unknown is null (shown as "—"), never 0.

  zingas-money run      the loop (supervisord runs it)
  zingas-money now      count and post once, now
  zingas-money show     print the count it would send; posts nothing
  zingas-money status   when the last post worked

Vault files Val keeps (never in git; examples in docs/SETUP-VAL.md, "Money tracker"):
  money/subscriptions.json   {"subscriptions": [{"id", "name", "cost", "cycle", "nextRenewal", "kind",
                              "personal", "plan", "receipts": [{"date", "amount"}], "lastUsed"}]}
  money/credits.json         {"left": 12.5, "asOf": "2026-10-20T10:00:00-04:00"}   (optional)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

sys.path.insert(0, "/usr/local/lib/zingas")
sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))

TZ = ZoneInfo("America/Indiana/Indianapolis") if ZoneInfo else timezone.utc   # the website's months, too
HERMES_HOME = os.environ.get("HERMES_HOME", "/root/.hermes")
VAULT = os.environ.get("ZINGAS_VAULT", "/root/Documents/ZingasVault")
STATE = os.path.join(HERMES_HOME, "money-state.json")
STATE_DB = os.path.join(HERMES_HOME, "state.db")
BACKUP_STATE = os.path.join(HERMES_HOME, "backup-state.json")
PRICES = os.environ.get("ZINGAS_MONEY_PRICES") or next(
    (p for p in ("/usr/local/lib/zingas/money_prices.json",
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), "money_prices.json"))
     if os.path.exists(p)), "/usr/local/lib/zingas/money_prices.json")
DOOR = "/api/assistant/cost"
UA = "zingas-money/1.0"
TIMEOUT = 25
EVERY = timedelta(minutes=60)
RETRY = timedelta(minutes=10)
LOOP_SLEEP = 300
RATE_DAYS = 7          # the pace for "days left" is the last 7 days
UNUSED_DAYS = 30
MAX_RUNWAY = 365       # "a year or more"
FOLLOWUP_EVENTS_KEPT = 400   # zingas_followups keeps only the newest 400 events

# The website's rules (app src/modules/assistant/cost.ts, parseCostCount). Kept the same here.
SERVICE_KINDS = ("ai", "texts", "plan", "storage", "tools", "other")
BASES = ("receipt", "count", "estimate")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_LIST = 60
MAX_DOLLARS = 100_000
RESULT_KEYS = ("texts", "draftsApproved", "followUps", "leadsAnswered")


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}", flush=True)


# ---------------------------------------------------------------- months (Indianapolis time)

def month_of(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%Y-%m")


def prev_month(month: str) -> str:
    y, m = (int(x) for x in month.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def next_month(month: str) -> str:
    y, m = (int(x) for x in month.split("-"))
    return f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"


def month_start(month: str) -> datetime:
    y, m = (int(x) for x in month.split("-"))
    return datetime(y, m, 1, tzinfo=TZ)


def month_end(month: str) -> datetime:
    return month_start(next_month(month))


def open_months(now: datetime) -> List[str]:
    """The months the website takes a count for: this month, and last month during the first 7 days."""
    local = now.astimezone(TZ)
    month = local.strftime("%Y-%m")
    return [month, prev_month(month)] if local.day <= 7 else [month]


def month_share(month: str, now: datetime, since: Optional[datetime] = None) -> float:
    """How much of the month has gone by, 0..1, counted from `since` (a service that started mid-month) or
    the 1st. At least one day, so the first hours don't make a wild run-rate."""
    start, end = month_start(month), month_end(month)
    if now >= end:
        return 1.0
    gone = max(now - max(start, since or start), timedelta(days=1))
    return min(1.0, gone / (end - start))


def cents(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x + 0.0, 2)


# ---------------------------------------------------------------- AI use from Hermes's state.db

def read_usage(db_path: str = STATE_DB, since: Optional[datetime] = None) -> Optional[List[dict]]:
    """Hermes's token counts, one row per session and model: provider, model, tokens, Hermes's own cost
    guess, and the time the use started and last happened. None when the database can't be read."""
    if not os.path.exists(db_path):
        return None
    since_ts = since.timestamp() if since else 0
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    except sqlite3.Error:
        return None
    try:
        tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        if "session_model_usage" in tables:
            q = ("select billing_provider, model, task, input_tokens, output_tokens, cache_read_tokens, "
                 "cache_write_tokens, estimated_cost_usd, first_seen, coalesce(last_seen, first_seen) "
                 "from session_model_usage where coalesce(last_seen, first_seen, 0) >= ?")
        elif "sessions" in tables:      # older Hermes: totals on the session itself
            q = ("select billing_provider, model, '', input_tokens, output_tokens, cache_read_tokens, "
                 "cache_write_tokens, estimated_cost_usd, started_at, coalesce(last_activity_at, ended_at, started_at) "
                 "from sessions where coalesce(last_activity_at, ended_at, started_at, 0) >= ?")
        else:
            return None
        rows = []
        for p, model, task, i, o, cr, cw, est, first, last in con.execute(q, (since_ts,)):
            rows.append({"provider": p or "", "model": model or "", "task": task or "", "input": i or 0,
                         "output": o or 0, "cacheRead": cr or 0, "cacheWrite": cw or 0, "hermesCost": est or 0,
                         "first": float(first or last or 0), "last": float(last or first or 0)})
        return rows
    except sqlite3.Error:
        return None
    finally:
        con.close()


def row_cost(row: dict, prices: dict) -> Optional[float]:
    """Dollars for one usage row: tokens x the price table; Hermes's own guess for a model not in the
    table; None when neither knows."""
    table = prices.get("ai", {}).get(row["provider"], {}).get("models", {}).get(row["model"])
    if table:
        return sum(row[k] * float(table.get(k, 0)) for k in ("input", "output", "cacheRead", "cacheWrite")) / 1e6
    if row.get("hermesCost", 0) > 0:
        return float(row["hermesCost"])
    if not any(row[k] for k in ("input", "output", "cacheRead", "cacheWrite")):
        return 0.0
    return None


def share(row: dict, a: datetime, b: datetime) -> float:
    """The part of a row's use that falls between a and b. A session's tokens are spread evenly from its
    first to its last call, so one long chat across midnight on the 1st is split between the two months."""
    first, last, lo, hi = row["first"], row["last"], a.timestamp(), b.timestamp()
    if last <= first:
        return 1.0 if lo <= last < hi else 0.0
    return max(0.0, min(last, hi) - max(first, lo)) / (last - first)


def ai_cost(rows: List[dict], prices: dict, provider: str, a: datetime, b: datetime) -> Optional[float]:
    """One provider's AI cost between a and b. None when a row with use in that time has no known price."""
    total = 0.0
    for r in rows:
        if r["provider"] != provider:
            continue
        part = share(r, a, b)
        if part <= 0:
            continue
        c = row_cost(r, prices)
        if c is None:
            return None
        total += c * part
    return total


# ---------------------------------------------------------------- vault files

def load_json(path: str):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def parse_day(value) -> Optional[date]:
    if not isinstance(value, str) or not DAY_RE.match(value.strip()):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def parse_when(value) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        d = parse_day(value)
        return datetime(d.year, d.month, d.day, tzinfo=TZ) if d else None
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def money_amount(value) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0 or value > MAX_DOLLARS:
        return None
    return float(value)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", text.strip().lower()).strip("-._")[:40]


def roll_forward(day: Optional[date], cycle: str, today: date) -> Optional[date]:
    """A renewal date already past moves on by its cycle, so a list Val hasn't touched still shows the next one."""
    if day is None:
        return None
    for _ in range(600):
        if day >= today:
            return day
        y, m = (day.year + 1, day.month) if cycle == "year" else (day.year + (day.month == 12), day.month % 12 + 1)
        try:
            day = date(y, m, min(day.day, 28 if m == 2 else 30 if m in (4, 6, 9, 11) else 31))
        except ValueError:
            return None
    return None


def load_subscriptions(data, today: date) -> List[dict]:
    """Val's subscription list, cleaned. A row that can't be read is left out (and logged), never guessed."""
    rows = data.get("subscriptions") if isinstance(data, dict) else data
    out, seen = [], set()
    for i, s in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(s, dict):
            continue
        name = s.get("name").strip()[:80] if isinstance(s.get("name"), str) and s["name"].strip() else ""
        sid = str(s.get("id") or "").strip().lower() or slug(name)
        cost = money_amount(s.get("cost"))
        if not name or not ID_RE.match(sid) or cost is None:
            log(f"subscriptions.json row {i + 1} left out: it needs a name, a short id and a cost")
            continue
        if sid in seen:
            continue
        seen.add(sid)
        cycle = s.get("cycle") if s.get("cycle") in ("month", "year") else "month"
        receipts = []
        for r in s.get("receipts") or []:
            d, amt = (parse_day(r.get("date")), money_amount(r.get("amount"))) if isinstance(r, dict) else (None, None)
            if d and amt is not None:
                receipts.append((d, amt))
        last_used = parse_day(s.get("lastUsed"))
        out.append({
            "id": sid, "name": name, "cost": cost, "cycle": cycle,
            "kind": s.get("kind") if s.get("kind") in SERVICE_KINDS else "plan",
            "personal": s.get("personal") is True, "plan": str(s.get("plan") or ""),
            "nextRenewal": roll_forward(parse_day(s.get("nextRenewal")), cycle, today),
            "receipts": receipts,
            "unused": bool(last_used and (today - last_used).days > UNUSED_DAYS),
        })
        if len(out) >= MAX_LIST:
            break
    return out


# ---------------------------------------------------------------- the lines

def nous_plan(prices: dict, subs: List[dict]) -> Tuple[float, float]:
    """(plan price a month, use included) for Nous: Gerrit's plan from his subscription list, else the
    usual plan in the price table. Pay as you go (0, 0) when neither says."""
    nous = prices.get("ai", {}).get("nous", {})
    sub = next((s for s in subs if s["id"] == "nous"), None)
    plan = nous.get("plans", {}).get((sub or {}).get("plan") or nous.get("defaultPlan", ""), {})
    monthly = sub["cost"] if sub else float(plan.get("monthly", 0))
    return monthly, float(plan.get("includedUsage", 0))


def ai_lines(rows: Optional[List[dict]], prices: dict, subs: List[dict], month: str, now: datetime) -> List[dict]:
    """One line per AI provider Val used this month. Nous: the plan plus use over what's included."""
    if rows is None:
        return [{"id": "nous", "name": prices.get("ai", {}).get("nous", {}).get("name", "Nous Portal"),
                 "kind": "ai", "billed": None, "runRate": None, "basis": "estimate"}]
    start, end = month_start(month), min(month_end(month), now)
    out = []
    for pid, info in prices.get("ai", {}).items():
        used = ai_cost(rows, prices, pid, start, end)
        # The pace counts from the first use this month: Val's first month began on Oct 21, not the 1st.
        first = min((r["first"] for r in rows if r["provider"] == pid and share(r, start, end) > 0), default=None)
        part = month_share(month, now, datetime.fromtimestamp(first, tz=TZ) if first else None)
        if pid == "nous":
            plan, included = nous_plan(prices, subs)
            billed = None if used is None else plan + max(0.0, used - included)
            pace = None if used is None else plan + max(0.0, used / part - included)
        elif info.get("includedIn"):
            if not used:      # the backup brain shows only in a month it was used
                continue
            billed = pace = 0.0
        else:
            if used == 0:
                continue
            billed, pace = used, (None if used is None else used / part)
        out.append({"id": pid, "name": info.get("name", pid)[:80], "kind": "ai", "billed": cents(billed),
                    "runRate": cents(pace), "basis": "estimate"})
    return out


def subscription_lines(subs: List[dict], month: str, skip: set) -> List[dict]:
    """A line for each fixed plan. Receipts this month: what was charged ("receipt"). None yet: a monthly
    plan's price stands in ("estimate"); a yearly plan costs nothing in a month it doesn't renew."""
    out = []
    for s in subs:
        if s["id"] in skip:
            continue
        paid = [amt for d, amt in s["receipts"] if d.strftime("%Y-%m") == month]
        if paid:
            billed, basis = sum(paid), "receipt"
        elif s["cycle"] == "month":
            billed, basis = s["cost"], "estimate"
        else:
            # Charged in the month it renews, or the month it was last paid (a year before the next renewal).
            nr = s["nextRenewal"]
            last_paid = nr.replace(year=nr.year - 1, day=min(nr.day, 28)) if nr else None
            charged = any(d is not None and d.strftime("%Y-%m") == month for d in (nr, last_paid))
            billed, basis = (s["cost"] if charged else 0.0), "estimate"
        line = {"id": s["id"], "name": s["name"], "kind": s["kind"], "billed": cents(billed), "basis": basis}
        if s["personal"]:
            line["personal"] = True
        out.append(line)
    return out


def subscriptions_list(subs: List[dict]) -> List[dict]:
    out = []
    for s in subs:
        row = {"id": s["id"], "name": s["name"], "cost": cents(s["cost"]), "cycle": s["cycle"],
               "nextRenewal": s["nextRenewal"].isoformat() if s["nextRenewal"] else None, "unused": s["unused"]}
        if s["personal"]:
            row["personal"] = True
        out.append(row)
    return out


def backblaze(state: Optional[dict], prices: dict, month: str, now: datetime) -> Tuple[Optional[dict], Optional[dict]]:
    """(service line, free-plan limit) for the backups. Nothing until the first backup has worked."""
    if not state or not state.get("last_ok"):
        return None, None
    b2 = prices.get("storage", {}).get("backblaze", {})
    stored = state.get("stored_bytes")
    exact = isinstance(stored, (int, float)) and stored > 0
    if not exact:
        stored = state.get("last_ok_bytes")
    if not isinstance(stored, (int, float)) or stored < 0:
        return None, None
    gb = stored / 1e9
    free, per = float(b2.get("freeGB", 10)), float(b2.get("perGBMonth", 0))
    pace = max(0.0, gb - free) * per
    line = {"id": "backblaze", "name": b2.get("name", "Backblaze B2"), "kind": "storage",
            "billed": cents(pace * month_share(month, now)), "runRate": cents(pace),
            "basis": "count" if exact else "estimate"}
    limit = {"name": "Backblaze", "used": round(gb, 2), "limit": free, "unit": "GB"}
    return line, limit


# ---------------------------------------------------------------- credits and days left

def nous_overage_after(rows: List[dict], prices: dict, since: datetime, now: datetime, included: float) -> Optional[float]:
    """Nous use paid from prepaid credits since `since`: in each month, only use past the included amount."""
    total, month = 0.0, month_of(since)
    while month_start(month) <= now:
        start, end = month_start(month), min(month_end(month), now)
        used = ai_cost(rows, prices, "nous", start, end)
        before = ai_cost(rows, prices, "nous", start, since) if since > start else 0.0
        if used is None or before is None:
            return None
        total += max(0.0, used - included) - max(0.0, before - included)
        month = next_month(month)
    return total


def runway(included_left: float, credits_left: float, daily: float, today: date, included: float) -> Optional[int]:
    """Whole days until Val runs out of Nous use at `daily` dollars a day. The included use refills on the
    1st. None when there is no use to measure a pace by; MAX_RUNWAY means a year or more."""
    if daily <= 0:
        return None
    pool, credit, day = included_left, credits_left, today
    for n in range(MAX_RUNWAY):
        spend = daily - min(pool, daily)
        pool = max(0.0, pool - daily)
        credit -= spend
        if credit < -1e-9:
            return n
        day += timedelta(days=1)
        if day.day == 1:
            pool = included
    return MAX_RUNWAY


def credits(rows: Optional[List[dict]], prices: dict, subs: List[dict], credit_file, now: datetime) -> Optional[dict]:
    """How much Nous use Val has left this month (included use plus prepaid credits) and how many days it
    lasts at the last 7 days' pace. Without money/credits.json, credits count as none (the name says so)."""
    if rows is None:
        return None
    month = month_of(now)
    _, included = nous_plan(prices, subs)
    used = ai_cost(rows, prices, "nous", month_start(month), now)
    if used is None:
        return {"name": "Nous use left", "left": None, "daysLeft": None}
    included_left = max(0.0, included - used)

    left, as_of = None, None
    if isinstance(credit_file, dict):
        left, as_of = money_amount(credit_file.get("left")), parse_when(credit_file.get("asOf"))
    if left is not None and as_of is not None and as_of <= now:
        spent = nous_overage_after(rows, prices, as_of, now, included)
        credits_left = None if spent is None else max(0.0, left - spent)
        name = "Nous use left (plan + credits)"
    else:
        credits_left, name = 0.0, "Nous use left (plan only; no credits on file)"
    if credits_left is None:
        return {"name": name, "left": None, "daysLeft": None}

    nous_rows = [r for r in rows if r["provider"] == "nous"]
    first = min((r["first"] for r in nous_rows), default=None)
    window = now - timedelta(days=RATE_DAYS)
    if first is not None:
        window = max(window, datetime.fromtimestamp(first, tz=timezone.utc))
    days = max((now - window) / timedelta(days=1), 1.0)
    recent = ai_cost(rows, prices, "nous", window, now)
    daily = (recent or 0.0) / days
    return {"name": name, "left": cents(included_left + credits_left),
            "daysLeft": runway(included_left, credits_left, daily, now.astimezone(TZ).date(), included)}


# ---------------------------------------------------------------- results

def followups_sent(state: Optional[dict], month: str) -> Optional[int]:
    """F0 follow-ups sent this month, from F0's own event list. None when that list can't say for sure
    (no list, or it was cut at 400 events inside this month)."""
    if not isinstance(state, dict) or not isinstance(state.get("events"), list):
        return None
    events = [(e, parse_when(e.get("at"))) for e in state["events"] if isinstance(e, dict)]
    oldest = events[0][1] if events else None
    if len(state["events"]) >= FOLLOWUP_EVENTS_KEPT and (oldest is None or oldest >= month_start(month)):
        return None
    return sum(1 for e, at in events
               if at and month_of(at) == month and str(e.get("what", "")).startswith("sent"))


# ---------------------------------------------------------------- one count

def make_count(month: str, now: datetime, prices: dict, usage: Optional[List[dict]], subs_data,
               backup_state: Optional[dict], followups_state: Optional[dict], credit_file,
               closing: bool = False) -> dict:
    """The count for `month`, ready to post. `closing` is last month's final count, sent in the first days
    of a new month: only its lines and results."""
    today = now.astimezone(TZ).date()
    subs = load_subscriptions(subs_data or {}, today)
    services = ai_lines(usage, prices, subs, month, now)
    services += subscription_lines(subs, month, skip={line["id"] for line in services} | {"quo-texts"})
    b2_line, b2_limit = backblaze(backup_state, prices, month, now)
    if b2_line and not any(s["id"] == "backblaze" for s in services):
        services.append(b2_line)
    count = {"month": month, "services": services[:MAX_LIST]}
    sent = followups_sent(followups_state, month)
    count["results"] = {"followUps": sent} if sent is not None else {}
    if not closing:
        count["subscriptions"] = subscriptions_list(subs)
        c = credits(usage, prices, subs, credit_file, now)
        if c:
            count["credits"] = c
        count["limits"] = [b2_limit] if b2_limit else []
    return count


def check_count(body, months: List[str]) -> Optional[str]:
    """The website's check (parseCostCount), the same rules: the reason it would refuse, or None."""
    def amount(o, key, where, top=MAX_DOLLARS, needed=False):
        v = o.get(key)
        if v is None:
            if needed:
                raise ValueError(f"{where}.{key} is needed.")
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or v > top:
            raise ValueError(f"{where}.{key} must be a number from 0 to {top}, or null.")
        return v

    def text(o, key, where):
        if not isinstance(o.get(key), str) or not o[key].strip():
            raise ValueError(f"{where}.{key} must be text.")

    def rows(key):
        v = body.get(key)
        if v is None:
            return []
        if not isinstance(v, list) or len(v) > MAX_LIST or not all(isinstance(x, dict) for x in v):
            raise ValueError(f"{key} must be a list of at most {MAX_LIST} objects.")
        return v

    def ids(items, key):
        seen = set()
        for i, x in enumerate(items):
            sid = x.get("id").strip().lower() if isinstance(x.get("id"), str) else ""
            if not ID_RE.match(sid):
                raise ValueError(f"{key}[{i}].id must be short lower-case letters, digits, dots or dashes.")
            if sid in seen:
                raise ValueError(f'{key} has "{sid}" twice.')
            seen.add(sid)

    try:
        if not isinstance(body, dict):
            raise ValueError("The body must be a JSON object.")
        if not isinstance(body.get("month"), str) or not MONTH_RE.match(body["month"]):
            raise ValueError("month must be YYYY-MM.")
        if body["month"] not in months:
            raise ValueError(f"month must be {' or '.join(months)}.")
        services = rows("services")
        ids(services, "services")
        for i, s in enumerate(services):
            w = f"services[{i}]"
            text(s, "name", w)
            if "kind" in s and s["kind"] not in SERVICE_KINDS:
                raise ValueError(f"{w}.kind must be one of {', '.join(SERVICE_KINDS)}.")
            if s.get("basis") not in BASES:
                raise ValueError(f"{w}.basis must be one of {', '.join(BASES)}.")
            amount(s, "billed", w)
            amount(s, "runRate", w)
        subs = rows("subscriptions")
        ids(subs, "subscriptions")
        for i, s in enumerate(subs):
            w = f"subscriptions[{i}]"
            text(s, "name", w)
            amount(s, "cost", w, needed=True)
            if "cycle" in s and s["cycle"] not in ("month", "year"):
                raise ValueError(f"{w}.cycle must be one of month, year.")
            nr = s.get("nextRenewal")
            if nr is not None and parse_day(nr) is None:
                raise ValueError(f"{w}.nextRenewal must be YYYY-MM-DD.")
        cr = body.get("credits")
        if cr is not None:
            if not isinstance(cr, dict):
                raise ValueError("credits must be an object.")
            text(cr, "name", "credits")
            amount(cr, "left", "credits")
            amount(cr, "daysLeft", "credits", top=3650)
        for i, lim in enumerate(rows("limits")):
            w = f"limits[{i}]"
            used, top = amount(lim, "used", w, top=1e12), amount(lim, "limit", w, top=1e12)
            if used is None or not top:
                raise ValueError(f"{w} needs used and a limit above 0.")
            text(lim, "name", w)
        res = body.get("results") if isinstance(body.get("results"), dict) else {}
        for k in RESULT_KEYS:
            amount(res, k, "results", top=1e7)
    except ValueError as e:
        return str(e)
    return None


# ---------------------------------------------------------------- posting

class PostError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}" if status else message)
        self.status = status


def website_settings() -> Tuple[str, str]:
    """(website address, Val's website key), from the environment or 1Password, as zingas-os reads them."""
    try:
        import zingas_os
        return zingas_os.read_secret("ZINGAS_OS_URL"), zingas_os.read_secret("ASSISTANT_API_TOKEN")
    except ImportError:
        return os.environ.get("ZINGAS_OS_URL", "").strip(), os.environ.get("ASSISTANT_API_TOKEN", "").strip()


def post_count(url: str, token: str, count: dict,
               opener: Callable = urllib.request.urlopen, timeout: float = TIMEOUT) -> dict:
    """POST one count to the website's door. Raises PostError with the website's reason when it refuses."""
    req = urllib.request.Request(url.rstrip("/") + DOOR, data=json.dumps(count).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                          "Accept": "application/json", "User-Agent": UA})
    try:
        with opener(req, timeout=timeout) as resp:
            out = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raise PostError(e.code, e.read().decode("utf-8", "replace")[:300].strip() or str(e.reason)) from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise PostError(0, f"no answer ({type(e).__name__})") from None
    if not isinstance(out, dict) or out.get("ok") is not True:
        raise PostError(0, "the website didn't say ok")
    return out


# ---------------------------------------------------------------- state and the loop

def load_state(path: str = STATE) -> dict:
    data = load_json(path)
    return data if isinstance(data, dict) else {}


def save_state(state: dict, path: str = STATE) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def due(state: dict, now: datetime) -> bool:
    last_ok, last_try = parse_when(state.get("last_ok")), parse_when(state.get("last_try"))
    if last_try and (not last_ok or last_try > last_ok) and now - last_try < RETRY:
        return False
    return last_ok is None or now - last_ok >= EVERY


def gather(now: datetime) -> dict:
    """Everything a count is made from, read from Val's computer."""
    since = month_start(prev_month(month_of(now))) - timedelta(days=1)
    credit_file = load_json(os.path.join(VAULT, "money", "credits.json"))
    as_of = parse_when(credit_file.get("asOf")) if isinstance(credit_file, dict) else None
    if as_of and as_of < since:
        since = month_start(month_of(as_of))
    return {"prices": load_json(PRICES) or {}, "usage": read_usage(STATE_DB, since),
            "subs_data": load_json(os.path.join(VAULT, "money", "subscriptions.json")),
            "backup_state": load_json(BACKUP_STATE),
            "followups_state": load_json(os.path.join(VAULT, "followups", "state.json")),
            "credit_file": credit_file}


def counts_to_send(now: datetime, state: dict, inputs: dict) -> List[dict]:
    """This month's count, and in the first 7 days also last month's final count (once it went through)."""
    months = open_months(now)
    out = []
    if len(months) == 2 and state.get("closed_month") != months[1]:
        out.append(make_count(months[1], now, closing=True, **inputs))
    out.append(make_count(months[0], now, **inputs))
    return out


def run_once(now: Optional[datetime] = None, state_path: str = STATE,
             settings: Callable[[], Tuple[str, str]] = website_settings,
             inputs_fn: Callable[[datetime], dict] = gather, opener: Callable = urllib.request.urlopen) -> dict:
    now = now or datetime.now(TZ)
    state = load_state(state_path)
    state["last_try"] = now.isoformat(timespec="seconds")
    url, token = settings()
    if not url or not token:
        state["last_error"] = "the website key or address is not set up (1Password: ASSISTANT_API_TOKEN, ZINGAS_OS_URL)"
        save_state(state, state_path)
        log("no count sent: " + state["last_error"])
        return state
    months = open_months(now)
    try:
        for count in counts_to_send(now, state, inputs_fn(now)):
            problem = check_count(count, months)
            if problem:
                raise PostError(0, f"the count for {count['month']} would be refused: {problem}")
            post_count(url, token, count, opener=opener)
            if count["month"] != months[0]:
                state["closed_month"] = count["month"]
            log(f"cost count sent for {count['month']}: {len(count['services'])} lines, "
                f"billed ${sum(s['billed'] or 0 for s in count['services']):.2f}")
        state.update(last_ok=now.isoformat(timespec="seconds"), last_month=months[0], last_error="")
    except PostError as e:
        state["last_error"] = str(e)[:300]
        log(f"cost count NOT sent: {state['last_error']}")
    save_state(state, state_path)
    return state


def run_loop() -> None:
    log("zingas-money started; a cost count about every hour")
    while True:
        now = datetime.now(TZ)
        if due(load_state(), now):
            run_once(now)
        time.sleep(LOOP_SLEEP)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="zingas-money", description="Val's hourly cost count for the website.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "now", "show", "status"):
        sub.add_parser(name)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run_loop()
    elif a.cmd == "now":
        return 0 if not run_once().get("last_error") else 1
    elif a.cmd == "show":
        now = datetime.now(TZ)
        counts = counts_to_send(now, load_state(), gather(now))
        for c in counts:
            print(json.dumps(c, indent=1))
            problem = check_count(c, open_months(now))
            print(f"The website would refuse this: {problem}" if problem else "The website would take this.")
    else:
        st = load_state()
        print(json.dumps({k: st.get(k, "") for k in ("last_ok", "last_try", "last_error", "last_month",
                                                       "closed_month")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
