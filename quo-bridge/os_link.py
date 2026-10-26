"""The link between quo-bridge and the company website (Zinga's OS).

The website keeps ONE do-not-contact list for everyone who texts customers
(Val, the estimator, people at the office). quo-bridge still keeps its own
flag in `contacts`, and with this link it also:
  - asks the website before every do-not-contact check, and
  - adds a number to the website's list when a customer texts STOP.

It is used only when both ZINGAS_OS_URL and ZINGAS_OS_TOKEN are set (see
build_bridge in app.py). Without them quo-bridge works exactly as before.

The rule is "never text when unsure": if the website can't be reached, answers
with an error, or answers with something we can't read, the number counts as
do-not-contact.

drafts_for_os() is what the website's door (GET /api/os/drafts) shows: the
drafts waiting on Gerrit, without full phone numbers. Gerrit's buttons there
come back through POST /api/os/drafts/action (Bridge.os_action).

Standard library only, like the rest of quo-bridge.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Iterable, List, Optional

from clients import USER_AGENT

TIMEOUT_SECONDS = 5.0
# After the website fails once, don't wait on it again for this long: every
# check in that time just counts as "unsure" (so: do not text). This keeps one
# outage from making each check wait the full timeout.
COOL_OFF_SECONDS = 30.0
# "planned": a follow-up still on its day's list card, waiting for Approve all (Gerrit, 2026-10-26: approve them on
# the website too, so a list is never only in one Telegram card).
OPEN_STATUSES = ("planned", "pending", "editing", "held", "countdown", "failed")


def last10(phone: str) -> str:
    """The website keys numbers by their last 10 digits: +13175550100 -> 3175550100."""
    return re.sub(r"\D", "", str(phone or ""))[-10:]


def _warn(what: str) -> None:
    # One line, never the phone number or the token.
    print(f"zingas-os: {what}", file=sys.stderr)


class OsLink:
    """Talks to the website's /api/assistant/contact door."""

    def __init__(self, url: str, token: str, timeout: float = TIMEOUT_SECONDS,
                 clock: Callable[[], float] = time.monotonic):
        self.url = url.rstrip("/") + "/api/assistant/contact"
        self.token = token
        self.timeout = timeout
        self.clock = clock
        self._quiet_until = 0.0

    def _call(self, method: str, query: str = "", body=None):
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/json",
                   "User-Agent": USER_AGENT}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        req = urllib.request.Request(self.url + query, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read() or b"null")

    def is_flagged(self, phone: str) -> Optional[bool]:
        """True or False as the website says, or None when we can't tell."""
        if self.clock() < self._quiet_until:
            return None
        digits = last10(phone)
        if len(digits) != 10:
            return None
        try:
            out = self._call("GET", "?phone=" + urllib.parse.quote(digits))
        except urllib.error.HTTPError as e:
            return self._unsure(f"HTTP {e.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return self._unsure(type(e).__name__)
        except ValueError:
            return self._unsure("answer was not JSON")
        if not isinstance(out, dict) or not isinstance(out.get("doNotContact"), bool):
            return self._unsure("answer had no doNotContact")
        return out["doNotContact"]

    def _unsure(self, reason: str) -> None:
        self._quiet_until = self.clock() + COOL_OFF_SECONDS
        _warn(f"do-not-contact check failed ({reason}); counting the number as do-not-contact")
        return None

    def add(self, phone: str) -> bool:
        """Put a number on the website's list. Never raises: returns False and logs on trouble."""
        digits = last10(phone)
        if len(digits) != 10:
            return False
        try:
            out = self._call("POST", body={"phone": digits})
        except urllib.error.HTTPError as e:
            _warn(f"adding to the do-not-contact list failed (HTTP {e.code})")
            return False
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            _warn(f"adding to the do-not-contact list failed ({type(e).__name__})")
            return False
        if not (isinstance(out, dict) and out.get("ok") is True):
            _warn("adding to the do-not-contact list: the website didn't say ok")
            return False
        return True


class SharedDncStore:
    """Wraps the real store. Everything goes straight to it, except the three
    do-not-contact methods, which also ask (or tell) the website."""

    def __init__(self, store, link: OsLink):
        self._store = store
        self.link = link

    def __getattr__(self, name):
        return getattr(self._store, name)

    def is_dnc(self, phone: str) -> bool:
        if self._store.is_dnc(phone):
            return True
        # None (unsure) counts as do-not-contact.
        return self.link.is_flagged(phone) is not False

    def dnc_phones(self, phones: Iterable[str]) -> List[str]:
        phones = list(phones)
        local = set(self._store.dnc_phones(phones))
        return [p for p in phones if p in local or self.link.is_flagged(p) is not False]

    def set_dnc(self, phone: str, flag: bool, at: str) -> None:
        # Our own flag first: it alone already stops every text from here.
        self._store.set_dnc(phone, flag, at)
        if flag:
            self.link.add(phone)
        # A START only clears our own flag. The website's list is cleared only
        # by a START texted to the estimator's number or by hand on the website,
        # so if the number is still on the website's list we still won't text it.


def drafts_for_os(store, limit: int = 100) -> dict:
    """The drafts still waiting on Gerrit, for the website. Never the full phone."""
    out = []
    for d in store.drafts_by_status(OPEN_STATUSES, limit):
        phone = d.get("phone") or ""
        out.append({
            "id": d["id"],
            "customer_name": d.get("customer_name"),
            "phone_last4": phone[-4:] if phone else "",
            "category": d.get("category"),
            "body": d.get("final_body") or d.get("body") or "",
            "customer_said": d.get("customer_said") or "",
            "status": d.get("status"),
            "reasons": d.get("reasons") or "",
            "created_at": d.get("created_at"),
            "send_after": d.get("send_after"),
            "edited": bool(d.get("edited")),
            # A follow-up with no phone is email only: its words can't be changed from the website.
            "can_edit": bool(phone),
            # Follow-ups: the day's list, the touch, when it sends, and the email that goes with it.
            "batch_id": d.get("batch_id") or "",
            "touch": d.get("touch") or "",
            "due_at": d.get("due_at"),
            "email_subject": (d.get("email_subject") or "")[:200] if d.get("email_to") else "",
            "email_body": (d.get("email_body") or "")[:2000] if d.get("email_to") else "",
        })
    return {"drafts": out}
