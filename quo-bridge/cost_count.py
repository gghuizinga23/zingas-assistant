"""quo-bridge's hourly cost count for the company website (Zinga's OS).

Once an hour, from the every-minute tick, quo-bridge counts the customer texts it sent this month and posts
one count to the website's door, POST {ZINGAS_OS_URL}/api/assistant/cost, with its own key ZINGAS_OS_TOKEN.
The website knows it is quo-bridge by that key, and for the line both senders may send (`quo-texts`)
quo-bridge's count wins. Shape: docs/CONNECTIONS.md, "Val's cost count".

  {"month": "2026-10",
   "services": [{"id": "quo-texts", "name": "Quo texts", "kind": "texts", "billed": 3.47, "runRate": 4.48,
                 "basis": "count"}],
   "results": {"texts": 347}}

How a text is counted (docs/PLAN.md, "Money: costs and ROI"): every draft with a `sent_at` this month
(Indianapolis time) and a phone and text, so email-only follow-ups are left out. A text is billed in
segments: up to 160 plain characters each, or 70 when it has an emoji or any other character outside the
plain text-message alphabet (even a curly quote). Rounded up, x $0.01. The run-rate is that scaled to a
full month. Nothing about a customer goes in the count.

The last post is kept in the `events` table ("cost_posted" / "cost_failed"), so it works across Vercel's
separate runs. A failed post is tried again after 10 minutes. Standard library only.
"""

from __future__ import annotations

import json
import math
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Callable, List, Optional
from zoneinfo import ZoneInfo

from clients import USER_AGENT
from store import parse_time, utc_iso

TZ = ZoneInfo("America/Indiana/Indianapolis")    # the website's months
DOOR = "/api/assistant/cost"
PRICE_PER_SEGMENT = 0.01      # Quo's price per text segment (public)
EVERY = timedelta(minutes=60)
RETRY = timedelta(minutes=10)
TIMEOUT_SECONDS = 8.0         # the tick has other work to do

# The plain text-message alphabet (GSM 03.38). Characters in EXTENDED take two places.
GSM_BASIC = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
GSM_EXTENDED = set("^{}\\[~]|€\f")


def segments(text: str) -> int:
    """How many billed parts one text is: length ÷ 160, or ÷ 70 with an emoji (or any other non-plain
    character), rounded up."""
    if not text:
        return 0
    if all(c in GSM_BASIC or c in GSM_EXTENDED for c in text):
        return math.ceil(sum(2 if c in GSM_EXTENDED else 1 for c in text) / 160)
    return math.ceil(len(text.encode("utf-16-le")) // 2 / 70)    # an emoji takes two places


# ---------------------------------------------------------------- months

def month_of(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%Y-%m")


def month_start(month: str) -> datetime:
    y, m = (int(x) for x in month.split("-"))
    return datetime(y, m, 1, tzinfo=TZ)


def month_end(month: str) -> datetime:
    y, m = (int(x) for x in month.split("-"))
    return datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=TZ)


def prev_month(month: str) -> str:
    y, m = (int(x) for x in month.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def open_months(now: datetime) -> List[str]:
    """The months the website takes a count for: this month, and last month during the first 7 days."""
    local = now.astimezone(TZ)
    month = local.strftime("%Y-%m")
    return [month, prev_month(month)] if local.day <= 7 else [month]


def month_share(month: str, now: datetime) -> float:
    """How much of the month has gone by, 0..1; at least one day, so a text on the 1st isn't a wild pace."""
    start, end = month_start(month), month_end(month)
    if now >= end:
        return 1.0
    return min(1.0, max(now - start, timedelta(days=1)) / (end - start))


# ---------------------------------------------------------------- the count

def make_count(rows: List[dict], month: str, now: datetime) -> dict:
    """The count for `month` from sent drafts (phone, body, final_body, sent_at)."""
    start, end = month_start(month), month_end(month)
    texts = parts = 0
    for d in rows:
        sent = parse_time(d.get("sent_at"))
        text = d.get("final_body") or d.get("body") or ""
        if not sent or not d.get("phone") or not text or not (start <= sent < end):
            continue
        texts += 1
        parts += segments(text)
    billed = round(parts * PRICE_PER_SEGMENT, 2)
    return {"month": month,
            "services": [{"id": "quo-texts", "name": "Quo texts", "kind": "texts", "billed": billed,
                          "runRate": round(parts * PRICE_PER_SEGMENT / month_share(month, now), 2),
                          "basis": "count"}],
            "results": {"texts": texts}}


class CostError(RuntimeError):
    pass


class CostPoster:
    """Posts a count to the website's door with quo-bridge's own key."""

    def __init__(self, url: str, token: str, opener: Callable = urllib.request.urlopen,
                 timeout: float = TIMEOUT_SECONDS):
        self.url = url.rstrip("/") + DOOR
        self.token, self.opener, self.timeout = token, opener, timeout

    def post(self, count: dict) -> None:
        req = urllib.request.Request(self.url, data=json.dumps(count).encode(), method="POST", headers={
            "Authorization": "Bearer " + self.token, "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": USER_AGENT})
        try:
            with self.opener(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            reason = e.read().decode("utf-8", "replace")[:200].strip()
            raise CostError(f"HTTP {e.code}" + (f": {reason}" if reason else "")) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise CostError(type(e).__name__) from None
        if not (isinstance(out, dict) and out.get("ok") is True):
            raise CostError("the website didn't say ok")


def hourly(store, poster: Optional[CostPoster], now: datetime) -> str:
    """Called every minute by the tick. Posts this month's count when an hour has gone by (and, on the first
    post of a new month, last month's final count first). Returns what it did; never raises."""
    if poster is None:
        return "off"
    try:
        last_ok = parse_time(store.last_event_at("cost_posted"))
        last_fail = parse_time(store.last_event_at("cost_failed"))
        if last_ok and now - last_ok < EVERY:
            return "not yet"
        if last_fail and (not last_ok or last_fail > last_ok) and now - last_fail < RETRY:
            return "waiting to try again"
        months = open_months(now)
        if len(months) == 2 and (last_ok is None or month_of(last_ok) != months[0]):
            months = [months[1], months[0]]      # close last month first
        else:
            months = months[:1]
        rows = store.sent_drafts_since(utc_iso(month_start(months[0])))
        sent = []
        for month in months:
            count = make_count(rows, month, now)
            poster.post(count)
            sent.append(f"{month}: {count['results']['texts']} texts")
        store.log("cost_posted", None, "; ".join(sent), utc_iso(now))
        return "posted"
    except CostError as e:
        _log_fail(store, str(e), now)
        return "failed"
    except Exception as e:      # a broken count must never stop the tick's real work
        _log_fail(store, type(e).__name__, now)
        return "failed"


def _log_fail(store, why: str, now: datetime) -> None:
    print(f"cost count: not sent ({why})", file=sys.stderr)
    try:
        store.log("cost_failed", None, why[:200], utc_iso(now))
    except Exception:
        pass
