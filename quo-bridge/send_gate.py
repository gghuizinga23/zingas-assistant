"""The customer-send gate for Zinga's Assistant.

Every text to a customer passes through decide() right before quo-bridge
calls Quo. The model never gets a way around it: these rules are code, not
prompt instructions. Pure functions, standard library only, covered by
test_send_gate.py.

Plain-English summary of the rules, in the order they are checked:
  1. Appointment confirmations never send. Corporate already sends them.
  2. Do-not-contact customers never get anything.
  3. Nothing sends outside 8am-8pm in the customer's time zone. An approved
     text waits until 8am instead.
  4. A text Gerrit approved sends.
  5. A text Gerrit did not approve sends by itself only when ALL of these hold:
       - it is an "on my way / running late" or a quick acknowledgment,
       - that type has earned auto-send (20 approvals in a row, no edits),
       - the customer is matched to a Salesforce Prospect,
       - it is short, and it mentions no money at all.
     Anything else waits for Gerrit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

# --- Tunable settings -------------------------------------------------------

SEND_WINDOW_START = time(8, 0)   # customer's local time
SEND_WINDOW_END = time(20, 0)    # no sends at or after 8pm

AUTO_SEND_CATEGORIES = frozenset({"on_my_way", "acknowledgment"})
NEVER_SEND_CATEGORIES = frozenset({"confirmation"})
AUTO_SEND_UNLOCK_STREAK = 20     # approvals in a row with no edits
AUTO_SEND_MAX_CHARS = 320        # auto-sent texts are short by nature

ESCALATE_AFTER = timedelta(minutes=10)
MISSED_AFTER = timedelta(hours=2)
GERRIT_TIME_ZONE = ZoneInfo("America/Indiana/Indianapolis")
GERRIT_WORKDAYS = frozenset({0, 1, 2, 3, 4})  # Monday to Friday

# --- Money check ------------------------------------------------------------
# Any of these in a text means it is about money, so it never sends by itself.
# Gerrit can still approve it by hand.

_NUMBER_WORDS = (
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|"
    r"fifty|sixty|seventy|eighty|ninety|hundred|thousand"
)

_MONEY_PATTERNS = [
    r"[$€£¢]",                                   # any currency sign
    r"\d\s*%",                                   # 10%, 10 %
    r"\bper\s*cent\b|\bpercent(age)?\b",
    r"\bdiscount(s|ed)?\b|\bmarkdown\b|\brebate\b|\bcoupon\b",
    r"\b\d+\s*off\b|\b(" + _NUMBER_WORDS + r")\s+(percent\s+)?off\b",
    r"\bdollars?\b|\bbucks?\b|\bgrand\b|\busd\b",
    r"\b\d+(\.\d+)?\s*k\b",                      # 5k, 2.5 k
    r"\b(hundred|thousand)s?\b",                 # two hundred, a thousand
    r"\b\d{1,3}(,\d{3})+(\.\d+)?\b",             # 1,250 or 12,500.00
    r"\b\d+\.\d{2}\b",                           # 199.99
    r"\bprice[sd]?\b|\bpricing\b|\bcosts?\b|\bcheaper\b|\bdeal\b|\bsavings?\b",
    r"\bpromo(tion)?s?\b|\bsale\b|\bfinanc(e|ing)\b|\bmonthly\b|\bpayments?\b",
    r"\bdeposit\b|\binterest\b|\bapr\b|\bbalance\b|\binvoice\b",
]
_MONEY_RE = re.compile("|".join(_MONEY_PATTERNS), re.IGNORECASE)


def money_terms(text: str) -> List[str]:
    """Every money-looking piece of the text (empty list means none found)."""
    return [m.group(0) for m in _MONEY_RE.finditer(text)]


# --- Inputs and outputs -----------------------------------------------------


@dataclass
class AutoSendStats:
    """How one message type is doing toward earning auto-send."""

    category: str
    approvals_in_a_row_unedited: int = 0
    enabled: bool = False

    def record_approval(self, edited: bool) -> None:
        """Call after Gerrit approves a draft of this type. An edit resets
        the streak and switches auto-send off until it is earned again."""
        if edited:
            self.approvals_in_a_row_unedited = 0
            self.enabled = False
            return
        self.approvals_in_a_row_unedited += 1
        if self.approvals_in_a_row_unedited >= AUTO_SEND_UNLOCK_STREAK:
            self.enabled = True

    def record_complaint(self) -> None:
        """A customer complaint or Gerrit saying 'stop doing that'."""
        self.approvals_in_a_row_unedited = 0
        self.enabled = False


@dataclass
class OutgoingText:
    text: str
    category: str                    # e.g. reply, followup, on_my_way, acknowledgment
    customer_time_zone: str          # IANA name, e.g. America/Chicago
    prospect_id: Optional[str]       # Salesforce Prospect ID, None if unmatched
    do_not_contact: bool = False
    approved_by_gerrit: bool = False


@dataclass
class Decision:
    action: str                      # "send", "hold", "needs_approval" or "block"
    reasons: List[str] = field(default_factory=list)
    send_after: Optional[datetime] = None   # set when action == "hold"

    @property
    def may_send_now(self) -> bool:
        return self.action == "send"


# --- The gate ---------------------------------------------------------------


def _next_window_open(local_now: datetime) -> datetime:
    start_today = local_now.replace(
        hour=SEND_WINDOW_START.hour, minute=SEND_WINDOW_START.minute,
        second=0, microsecond=0,
    )
    return start_today if local_now < start_today else start_today + timedelta(days=1)


def decide(msg: OutgoingText, now: datetime,
           stats: Optional[AutoSendStats] = None) -> Decision:
    """Decide what happens to one outgoing customer text. `now` must be
    timezone-aware."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    if msg.category in NEVER_SEND_CATEGORIES:
        return Decision("block", ["Appointment confirmations never send: corporate already sends them."])
    if msg.do_not_contact:
        return Decision("block", ["This customer is marked do not contact."])
    if not msg.text.strip():
        return Decision("block", ["The text is empty."])

    try:
        tz = ZoneInfo(msg.customer_time_zone)
    except Exception:
        return Decision("block", [f"Unknown time zone: {msg.customer_time_zone!r}."])

    local_now = now.astimezone(tz)
    in_window = SEND_WINDOW_START <= local_now.time() < SEND_WINDOW_END

    if msg.approved_by_gerrit:
        if in_window:
            return Decision("send", ["Approved by Gerrit."])
        return Decision(
            "hold",
            ["Approved, but it is outside 8am-8pm for the customer. It waits until 8am."],
            send_after=_next_window_open(local_now),
        )

    # Not approved: only a narrow kind of text may go by itself.
    reasons: List[str] = []
    if msg.category not in AUTO_SEND_CATEGORIES:
        reasons.append(f"'{msg.category}' texts always need Gerrit's OK.")
    elif stats is None or stats.category != msg.category or not stats.enabled:
        reasons.append(f"'{msg.category}' has not earned auto-send yet "
                       f"({AUTO_SEND_UNLOCK_STREAK} approvals in a row with no edits).")
    if not msg.prospect_id:
        reasons.append("The customer is not matched to a Salesforce Prospect.")
    if len(msg.text) > AUTO_SEND_MAX_CHARS:
        reasons.append(f"Too long to send by itself ({len(msg.text)} characters).")
    found = money_terms(msg.text)
    if found:
        reasons.append("Mentions money (" + ", ".join(sorted(set(found), key=str.lower)) + ").")
    if not in_window:
        reasons.append("Outside 8am-8pm for the customer.")

    if reasons:
        return Decision("needs_approval", reasons)
    return Decision("send", [f"Auto-send: '{msg.category}' has earned it and passed every check."])


# --- Waiting drafts ---------------------------------------------------------


def _business_time_between(start: datetime, end: datetime) -> timedelta:
    """How much of [start, end) falls in Gerrit's working hours (weekdays,
    8am-8pm Indianapolis). Overnight and weekend waits don't count, so an 11pm
    draft does not fire an alert at 11:10pm."""
    if end <= start:
        return timedelta(0)
    total = timedelta(0)
    cur = start.astimezone(GERRIT_TIME_ZONE)
    end_local = end.astimezone(GERRIT_TIME_ZONE)
    while cur < end_local:
        day_start = cur.replace(hour=SEND_WINDOW_START.hour, minute=0, second=0, microsecond=0)
        day_end = cur.replace(hour=SEND_WINDOW_END.hour, minute=0, second=0, microsecond=0)
        if cur.weekday() in GERRIT_WORKDAYS:
            lo = max(cur, day_start)
            hi = min(end_local, day_end)
            if hi > lo:
                total += hi - lo
        cur = (cur + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return total


def waiting_status(created_at: datetime, now: datetime, handled: bool) -> str:
    """For a customer draft waiting on Gerrit: 'ok', 'escalate' (text Gerrit's cell
    from the Quo number) or 'missed' (show in the next brief)."""
    if handled:
        return "ok"
    waited = _business_time_between(created_at, now)
    if waited >= MISSED_AFTER:
        return "missed"
    if waited >= ESCALATE_AFTER:
        return "escalate"
    return "ok"
