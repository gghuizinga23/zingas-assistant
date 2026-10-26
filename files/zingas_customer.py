#!/usr/bin/env python3
"""zingas_customer: one file per customer. Plain code, no AI of its own.

Every program that sees a customer contact (texts, calls and voicemails in zingas-quo, emails in
zingas-inbox, visit recordings in zingas-plaud) goes through this module, so each customer has one place
that holds everything. All of it lives in Val's vault, never in git (docs/VAL-BRAIN.md, Part 1):

  customers/<ProspectID>.md         the profile: who they are, the facts Val learned, "Where the sale is"
                                    and "Last 5 contacts" at the top
  history/<ProspectID>.md           the timeline: one dated entry per contact, newest last, append-only
  visits/<ProspectID>/<date>-<id>.md  the full visit transcripts (written by zingas-plaud)

A number that no customer file knows is kept under the key unmatched-<10 digits>. When that number is
matched later, its timeline, facts and visits move to the customer's files by themselves.

  resolve(phone=, email=)   -> Prospect ID: phone first, then email, then the quote follow-up list
                               (which knows phone and email from the appointment emails), then the
                               company website's Salesforce match. Never a name alone.
  log(key, channel, when, summary, ref)  -> adds one timeline entry and refreshes "Last 5 contacts"
  add_facts(key, facts, source)          -> new facts in the profile, each tagged with where it came from
  context(key)                           -> profile + the last 15 contacts + the newest visit, for a prompt
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

import sys
sys.path.insert(0, "/usr/local/lib/zingas")
sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))
import zingas_todo as zt  # noqa: E402

VAULT = os.environ.get("ZINGAS_VAULT", "/root/Documents/ZingasVault")
TZ = zt.TZ

CHANNELS = {
    "visit": "Visit",
    "text_in": "Text in",
    "text_out": "Text out",
    "missed_call": "Missed call",
    "voicemail": "Voicemail",
    "call": "Call",
    "email_in": "Email in",
    "email_out": "Email out",
    "note": "Note",
}
FROM_CUSTOMER = {"text_in", "missed_call", "voicemail", "call", "email_in", "visit"}

# Profile sections Val's programs fill. The first five are Gerrit's Part 4 picks (ideas 1 to 5).
FACT_SECTIONS = {
    "talk": "How they talk",
    "life_events": "Life events",
    "house": "The house",
    "gerrit_said": "What Gerrit said",
    "mood": "Mood over time",
    "people": "People and who decides",
    "products": "Products and rooms",
    "likes": "What they like",
    "worries": "Worries and objections",
    "timing": "Timing",
    "personal": "Personal details",
}
KEEP_FACTS = 12            # newest bullets kept per section
KEEP_MOODS = 8
SALE_SECTION = "Where the sale is"
LAST_SECTION = "Last 5 contacts"
CONTEXT_ENTRIES = 15
MONEY = re.compile(r"\$\s?\d|\d[\d,.]*\s?(dollars|bucks|k\b)", re.I)
PHONE_RUN = re.compile(r"\+?1?[\s.-]*\(?\d{3}\)?[\s.-]*\d{3}[\s.-]*\d{4}")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,60}$")
HEAD_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) · ([^·]+?)(?: · (.*))?$")


# ------------------------------------------------------------------ helpers

def digits10(phone) -> str:
    d = re.sub(r"\D", "", str(phone or ""))
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d if len(d) == 10 else ""


def pretty(phone) -> str:
    d = digits10(phone)
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if d else str(phone or "")


def unmatched_key(phone) -> str:
    d = digits10(phone)
    return "unmatched-" + d if d else ""


def is_unmatched(key: str) -> bool:
    return str(key or "").startswith("unmatched-")


def safe_key(key) -> str:
    """A Prospect ID or unmatched key that is safe to use as a file name, or ""."""
    key = str(key or "").strip()
    return key if KEY_RE.match(key) else ""


def one_line(text, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


def short_date(dt: datetime) -> str:
    """10/23/26, the house format."""
    return f"{dt.month}/{dt.day}/{dt:%y}"


def _when(value) -> datetime:
    t = zt.when(value) if not isinstance(value, datetime) else value
    t = t or datetime.now(timezone.utc)
    return (t if t.tzinfo else t.replace(tzinfo=TZ)).astimezone(TZ)


def paths(key: str, vault: str = VAULT) -> Dict[str, str]:
    key = safe_key(key)
    if not key:
        raise ValueError("not a customer key")
    return {"profile": os.path.join(vault, "customers", key + ".md"),
            "history": os.path.join(vault, "history", key + ".md"),
            "visits": os.path.join(vault, "visits", key)}


def _read(path: str, limit: int = 0) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return ""
    return text[:limit] if limit else text


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-", suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


@contextlib.contextmanager
def _locked(vault: str):
    """One writer at a time across Val's programs (texts, email, recordings)."""
    folder = os.path.join(vault, "history")
    os.makedirs(folder, mode=0o700, exist_ok=True)
    with open(os.path.join(folder, ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


# ------------------------------------------------------------- finding people

def _profiles(vault: str) -> Iterable[Tuple[str, str, str]]:
    folder = os.path.join(vault, "customers")
    if not os.path.isdir(folder):
        return
    for name in sorted(os.listdir(folder)):
        if name.endswith(".md") and safe_key(name[:-3]):
            p = os.path.join(folder, name)
            yield name[:-3], p, _read(p)


def find_by_phone(phone, vault: str = VAULT, include_unmatched: bool = False) -> str:
    want = digits10(phone)
    if not want:
        return ""
    for key, _, body in _profiles(vault):
        if is_unmatched(key) and not include_unmatched:
            continue
        if any(digits10(run) == want for run in PHONE_RUN.findall(body)):
            return key
    return ""


def find_by_email(email, vault: str = VAULT) -> str:
    want = str(email or "").strip().lower()
    if not EMAIL_RE.fullmatch(want):
        return ""
    for key, _, body in _profiles(vault):
        if not is_unmatched(key) and want in {e.lower() for e in EMAIL_RE.findall(body)}:
            return key
    return ""


def followup_people(vault: str = VAULT) -> List[dict]:
    """The people F0 knows from the appointment and estimate emails: name, phone, email, visit time."""
    try:
        with open(os.path.join(vault, "followups", "state.json")) as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        return []
    out = []
    for c in (st.get("customers") or {}).values():
        out.append({"name": c.get("name") or "", "phone": c.get("phone") or "", "email": c.get("email") or "",
                    "time_zone": c.get("time_zone") or "", "appt_at": c.get("appt_at") or ""})
    return out


def appointments(vault: str = VAULT) -> List[dict]:
    """Every "Appt on ..." email F0 has read: time, name, phone, time zone."""
    try:
        with open(os.path.join(vault, "followups", "state.json")) as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        return []
    return [a for a in (st.get("appointments") or {}).values() if isinstance(a, dict) and a.get("at")]


def ensure_profile(pid: str, vault: str = VAULT, name: str = "", phone: str = "", email: str = "") -> str:
    """The profile for this Prospect ID, made if it isn't there. Adds a phone or email it doesn't have yet."""
    p = paths(pid, vault)["profile"]
    body = _read(p)
    if not body:
        title = one_line(name, 80) or ("Unmatched number " + pretty(phone) if is_unmatched(pid) else pid)
        body = f"# {title}\n\n"
        body += ("status: unmatched\n" if is_unmatched(pid) else f"Prospect ID: {pid}\n")
    add = []
    if digits10(phone) and not any(digits10(r) == digits10(phone) for r in PHONE_RUN.findall(body)):
        add.append(f"phone: {pretty(phone)}")
    if EMAIL_RE.fullmatch(str(email or "").strip()) and email.lower() not in body.lower():
        add.append(f"email: {email.strip().lower()}")
    if add or not os.path.exists(p):
        lines = body.rstrip("\n").split("\n")
        at = next((k + 1 for k, row in enumerate(lines) if row.startswith(("Prospect ID:", "status:"))), len(lines))
        lines[at:at] = add
        _write(p, "\n".join(lines) + "\n")
    return p


def resolve(phone="", email="", vault: str = VAULT, sf: Optional[dict] = None) -> str:
    """The customer's Prospect ID, or "" when Val can't be sure. Never matches on a name alone.
    sf: the company website's one matched Salesforce customer for this phone, when the caller asked."""
    key = find_by_phone(phone, vault) if phone else ""
    if not key and email:
        key = find_by_email(email, vault)
        if not key:   # the follow-up list knows email and phone together, from the appointment email
            for c in followup_people(vault):
                if c["email"].lower() == str(email).strip().lower() and digits10(c["phone"]):
                    key = find_by_phone(c["phone"], vault)
                    if key:
                        ensure_profile(key, vault, email=email)
                        phone = phone or c["phone"]
                    break
    if not key and sf and safe_key(sf.get("prospectId")) and not is_unmatched(sf["prospectId"]):
        key = sf["prospectId"]
        ensure_profile(key, vault, name=sf.get("name") or "", phone=phone, email=email)
    if key and phone:
        move_unmatched(phone, key, vault)
    return key


def key_for(phone="", email="", vault: str = VAULT, sf: Optional[dict] = None) -> str:
    """The Prospect ID, else unmatched-<digits> for a phone, else ""."""
    return resolve(phone, email, vault, sf) or unmatched_key(phone)


# ------------------------------------------------------------------ sections

def get_section(text: str, heading: str) -> List[str]:
    lines, out, inside = text.split("\n"), [], False
    for row in lines:
        if row.startswith("## "):
            if inside:
                break
            inside = row[3:].strip() == heading
            continue
        if inside and (row.startswith("# ") or not row.strip()):
            break           # Val's sections end at their first blank line; text after it is Gerrit's
        if inside:
            out.append(row)
    return out


def set_section(text: str, heading: str, body: List[str], top: bool = False) -> str:
    """Replace the "## heading" section's lines, or add the section (at the top, under the title, or at the end)."""
    lines = text.rstrip("\n").split("\n") if text.strip() else []
    block = [f"## {heading}"] + list(body) + [""]
    start = next((k for k, r in enumerate(lines) if r.startswith("## ") and r[3:].strip() == heading), None)
    if start is not None:
        end = next((k for k in range(start + 1, len(lines))
                    if lines[k].startswith(("## ", "# ")) or not lines[k].strip()), len(lines))
        block = block[:-1] if end < len(lines) and not lines[end].strip() else block
        lines[start:end] = block
    elif top:
        title = next((k for k, r in enumerate(lines) if r.startswith("# ")), -1)
        at = title + 1
        while at < len(lines) and lines[at].strip() and not lines[at].startswith("#"):
            at += 1          # keep the key lines (Prospect ID, phone, email) right under the title
        lines[at:at] = ([""] if at and lines[at - 1].strip() else []) + block
    else:
        lines += ([""] if lines and lines[-1].strip() else []) + block
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).rstrip("\n") + "\n"


# ------------------------------------------------------------------ timeline

def _entries(text: str) -> List[dict]:
    out, cur = [], None
    for row in text.split("\n"):
        m = HEAD_RE.match(row)
        if m:
            cur = {"at": m.group(1), "channel": m.group(2).strip(), "who": (m.group(3) or "").strip(),
                   "lines": [], "refs": []}
            out.append(cur)
        elif cur is not None and row.startswith("ref: "):
            cur["refs"].append(row[5:].strip())
        elif cur is not None and row.strip():
            cur["lines"].append(row)
    return out


def _render_entries(title: str, entries: List[dict]) -> str:
    out = [f"# Timeline: {title}", "", "_Kept by Val's programs. One entry per contact, newest last._", ""]
    for e in entries:
        out.append(f"### {e['at']} · {e['channel']}" + (f" · {e['who']}" if e.get("who") else ""))
        out += e["lines"]
        out += [f"ref: {r}" for r in e["refs"]]
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def _clean_lines(summary: str, limit_lines: int = 3) -> List[str]:
    rows = []
    for row in str(summary or "").replace("\r", "").split("\n"):
        row = one_line(row, 400).lstrip("#").strip()
        if row.lower().startswith("ref:"):
            row = "(ref) " + row[4:].strip()
        if row:
            rows.append(row)
    return rows[:limit_lines] or ["(nothing to show)"]


def title_of(key: str, vault: str = VAULT) -> str:
    for row in _read(paths(key, vault)["profile"], 2000).split("\n"):
        if row.startswith("# "):
            return one_line(row[2:], 80)
    return key


def log(key: str, channel: str, when, summary: str, ref: str = "", who: str = "", full: str = "",
        extra: Iterable[str] = (), vault: str = VAULT) -> bool:
    """One timeline entry. Returns False when the same ref is already there (a retry), or the key is bad."""
    key = safe_key(key)
    if not key:
        return False
    p = paths(key, vault)
    label = CHANNELS.get(channel, one_line(channel, 30) or "Note")
    at = _when(when).strftime("%Y-%m-%d %H:%M")
    with _locked(vault):
        entries = _entries(_read(p["history"]))
        if ref and any(ref in e["refs"] for e in entries):
            return False
        lines = _clean_lines(summary) + [one_line(x, 300) for x in extra if one_line(x, 300)][:12]
        if full:
            lines.append(f"Full text: {full}")
        entries.append({"at": at, "channel": label, "who": one_line(who, 60).replace("·", "-"), "lines": lines,
                        "refs": [one_line(ref, 200)] if ref else []})
        entries.sort(key=lambda e: e["at"])       # stable: same minute keeps the order they came in
        if not os.path.exists(p["profile"]):
            ensure_profile(key, vault)
        _write(p["history"], _render_entries(title_of(key, vault), entries))
        _refresh_last5(key, entries, vault)
    return True


def timeline(key: str, vault: str = VAULT) -> List[dict]:
    key = safe_key(key)
    return _entries(_read(paths(key, vault)["history"])) if key else []


def _mask_phones(text: str) -> str:
    """Phone numbers stay out of the profile's contact lines, so a number someone mentions in passing
    never makes their file match that number."""
    return PHONE_RUN.sub("(number)", text)


def _refresh_last5(key: str, entries: List[dict], vault: str) -> None:
    p = paths(key, vault)["profile"]
    body = _read(p)
    rows = []
    for e in entries[-5:][::-1]:
        first = e["lines"][0] if e["lines"] else ""
        rows.append(_mask_phones(f"- {e['at']} {e['channel']}" + (f" ({e['who']})" if e["who"] else "")
                                 + f": {one_line(first, 140)}"))
    _write(p, set_section(body, LAST_SECTION, rows, top=True))


# ------------------------------------------------------------------ facts

def _fact_text(value) -> str:
    if isinstance(value, dict):        # a life event: {"what": ..., "date": ...}
        what, date = one_line(value.get("what"), 180), one_line(value.get("date"), 20)
        return f"{what} ({date})" if what and date else what
    return one_line(value, 200)


def add_facts(key: str, facts: Optional[dict], source: str, vault: str = VAULT) -> int:
    """New facts into the profile, each tagged with its source ("recording 10/23/26", "text 10/24/26").
    Repeats are skipped. Never a price. Returns how many were added."""
    key = safe_key(key)
    if not key or not isinstance(facts, dict):
        return 0
    source = one_line(source, 40)
    added = 0
    with _locked(vault):
        p = paths(key, vault)["profile"]
        if not os.path.exists(p):
            ensure_profile(key, vault)
        body = _read(p)
        for field, heading in FACT_SECTIONS.items():
            raw = facts.get(field)
            values = [raw] if isinstance(raw, (str, dict)) else list(raw or []) if isinstance(raw, list) else []
            new = [t for t in (_fact_text(v) for v in values) if t and not MONEY.search(t)]
            if not new:
                continue
            rows = get_section(body, heading)
            have = {re.sub(r"\s*\([^()]*\)\s*$", "", r[2:]).strip().lower() for r in rows if r.startswith("- ")}
            for t in new:
                if t.lower() in have:
                    continue
                have.add(t.lower())
                rows.append(f"- {t} ({source})")
                added += 1
            body = set_section(body, heading, rows[-(KEEP_MOODS if field == "mood" else KEEP_FACTS):])
        _write(p, body)
    return added


def set_sale_stage(key: str, stage: str, source: str, vault: str = VAULT) -> None:
    key, stage = safe_key(key), one_line(stage, 240)
    if not key or not stage or MONEY.search(stage):
        return
    with _locked(vault):
        p = paths(key, vault)["profile"]
        if not os.path.exists(p):
            ensure_profile(key, vault)
        _write(p, set_section(_read(p), SALE_SECTION, [f"{stage} ({one_line(source, 40)})"], top=True))


# ------------------------------------------------------------------ unmatched

def move_unmatched(phone, pid: str, vault: str = VAULT) -> bool:
    """A number that was unmatched now belongs to pid: move its timeline, facts and visits over."""
    uk, pid = unmatched_key(phone), safe_key(pid)
    if not uk or not pid or is_unmatched(pid):
        return False
    old, new = paths(uk, vault), paths(pid, vault)
    if not any(os.path.exists(x) for x in old.values()):
        return False
    with _locked(vault):
        entries = _entries(_read(new["history"]))
        refs = {r for e in entries for r in e["refs"]}
        moved = [e for e in _entries(_read(old["history"])) if not (set(e["refs"]) & refs)]
        if not os.path.exists(new["profile"]):
            ensure_profile(pid, vault, phone=phone)
        if moved:
            entries = sorted(entries + moved, key=lambda e: e["at"])
            _write(new["history"], _render_entries(title_of(pid, vault), entries))
            _refresh_last5(pid, entries, vault)
        stub = _read(old["profile"])
        body = _read(new["profile"])
        for heading in list(FACT_SECTIONS.values()) + [SALE_SECTION]:
            rows = get_section(stub, heading)
            if rows:
                mine = get_section(body, heading)
                body = set_section(body, heading, mine + [r for r in rows if r not in mine],
                                   top=heading == SALE_SECTION)
        _write(new["profile"], body)
        if os.path.isdir(old["visits"]):
            os.makedirs(new["visits"], mode=0o700, exist_ok=True)
            for name in os.listdir(old["visits"]):
                shutil.move(os.path.join(old["visits"], name), os.path.join(new["visits"], name))
            os.rmdir(old["visits"])
        for x in (old["history"], old["profile"]):
            if os.path.exists(x):
                os.remove(x)
    return True


# ------------------------------------------------------------------ reading

def newest_visit(key: str, vault: str = VAULT) -> str:
    folder = paths(key, vault)["visits"]
    try:
        names = sorted(n for n in os.listdir(folder) if n.endswith(".md"))
    except OSError:
        return ""
    if not names:
        return ""
    text = _read(os.path.join(folder, names[-1]))
    return text.split("\n## Transcript", 1)[0].strip()      # the summary part, not the whole transcript


def last_heard(entries: List[dict], now: Optional[datetime] = None) -> str:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    ins = [e for e in entries if e["channel"] in {CHANNELS[c] for c in FROM_CUSTOMER}]
    outs = [e for e in entries if e["channel"] in (CHANNELS["text_out"], CHANNELS["email_out"])]
    if not ins:
        return "Val has no contact from this customer on file yet."
    last = ins[-1]
    days = (now.date() - datetime.strptime(last["at"][:10], "%Y-%m-%d").date()).days
    line = f"Last contact from the customer: {days} day(s) ago ({last['channel'].lower()}, {last['at'][:10]})."
    if outs and outs[-1]["at"] > last["at"]:
        line += " Gerrit's side wrote last, and the customer has not answered yet."
    return line


def context(key: str, vault: str = VAULT, max_chars: int = 12000, now: Optional[datetime] = None) -> str:
    """What Val reads before she drafts or judges: the profile, the last 15 contacts and the newest visit.
    "" when there is no file for this key."""
    key = safe_key(key)
    if not key:
        return ""
    profile = _read(paths(key, vault)["profile"])
    entries = timeline(key, vault)
    if not profile and not entries:
        return ""
    parts = ["## Customer file (" + ("unmatched number" if is_unmatched(key) else f"Prospect ID {key}") + ")",
             profile[:6000].strip() or "(no profile yet)"]
    if entries:
        parts.append(f"## The last {min(len(entries), CONTEXT_ENTRIES)} contacts (oldest first)")
        for e in entries[-CONTEXT_ENTRIES:]:
            head = f"- {e['at']} {e['channel']}" + (f" ({e['who']})" if e["who"] else "") + ": "
            parts.append(head + " / ".join(x for x in e["lines"] if not x.startswith("Full text:"))[:600])
        parts.append(last_heard(entries, now))
    visit = newest_visit(key, vault)
    if visit:
        parts.append("## The newest visit (summary)\n" + visit[:3000])
    out = "\n".join(parts)
    return out if len(out) <= max_chars else out[:max_chars - 20] + "\n(cut for length)"
