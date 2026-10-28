#!/usr/bin/env python3
"""zingas-desk: Val's desk on the website (Zinga's OS > Assistant). Plain code; the only AI is Val herself,
answering Gerrit's website messages in her own Telegram conversation.

Gerrit's ask (2026-10-28): everything he does with Val in Telegram he can also do on the website, from an iPad or
a computer. Val's computer stays closed to the internet, so this program asks the website every 10 seconds
(GET /api/assistant/desk, Val's key ASSISTANT_API_TOKEN) and posts back (POST /api/assistant/desk):

  - Val's questions with buttons ("Is this task done too?" Yes / No) go to Needs you; his answer comes back here
    and is made the same way as his Telegram answer.
  - What Gerrit types on Talk to Val goes into Val's own Telegram conversation (one shared conversation); her
    answer goes to Telegram too, and every Telegram turn is copied to the website.
  - Every note Val sends Gerrit (new tasks, hot leads, problems ...) is copied to From Val, and Telegram gets it
    only when Settings > Alerts says so for that kind.
  - Her morning brief and evening wrap-up are copied to From Val, and her programs' health to Activity.
  - Settings (programs on or off, Gerrit's answers and links, timing, follow-up rules) are kept here
    (vault desk/settings.json) for her other programs to read. Pause all customer texts is not hers: quo-bridge
    holds the texts.

Her other programs never wait on the website: note(), ask() and close() only add a line to desk/outbox.jsonl and
never raise; this program sends it. With no saved settings yet, every program runs as it does today.

  zingas-desk run                       the loop (supervisord runs it)
  zingas-desk ask --id ID --kind KIND --question-file - [--option key=Label ...] [--text]
  zingas-desk close --id ID [--note "Done."]
  zingas-desk note --kind KIND --text-file -
  zingas-desk settings                  what Val has now (no customer data in it)
  zingas-desk check                     one test call; prints only whether it worked

No prices, ever. Customers by first name at most in a question. Customer details never go in the logs.
Installed at /usr/local/lib/zingas/zingas_desk.py and /usr/local/bin/zingas-desk.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time as _time
from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, "/usr/local/lib/zingas")
sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))

VAULT = os.environ.get("ZINGAS_VAULT", "/root/Documents/ZingasVault")
DOOR = "/api/assistant/desk"
EVERY = 10                                   # seconds between looks
MIRROR_EVERY = timedelta(seconds=30)         # Telegram turns copied to the website
SLOW_EVERY = timedelta(minutes=2)            # briefs and health
OUTBOX_MAX = 500                             # lines kept when the website is away (oldest notes go first)
FIRST_MIRROR = 40                            # turns copied the first time a conversation is seen
WEB_MARK = "[From the website] "             # how Val knows a turn came from the website
COPY_MARK = "💻 On the website you said:"       # the Telegram copy of a website turn (not copied back)
CHAT_TIMEOUT = 420

# ------------------------------------------------------------------ settings (the website's DEFAULT_SETTINGS)

PROGRAMS = ("followups", "thanks", "installs", "missed_call", "hotleads", "plaud", "inbox")
ALERT_KINDS = ("question", "new_task", "hot_lead", "problem", "watchdog", "brief", "note")
ROUTES = ("both", "telegram", "ipad", "none")
TOUCHES = (("48 hours", 2), ("7 days", 7), ("day 14", 14), ("day 21", 21), ("day 28", 28), ("day 42", 42),
           ("day 56", 56), ("day 70", 70), ("day 84", 84), ("day 90", 90))
DEFAULTS = {
    "paused": False,
    "autoSend": False,
    "programs": {p: True for p in PROGRAMS},
    "answers": {},
    "links": {"reviewLink": "", "referralReward": ""},
    "timing": {"recordingWaitMinutes": 120, "callbackFrom": 9, "callbackTo": 19, "callbackSaturday": True},
    "alerts": {"question": "both", "new_task": "telegram", "hot_lead": "both", "problem": "both",
               "watchdog": "both", "brief": "telegram", "note": "telegram"},
    "followups": {"touches": [{"key": k, "days": d, "on": True, "send": "both"} for k, d in TOUCHES],
                  "quietDays": 3, "listAt": "08:01"},
}


def paths(vault: Optional[str] = None) -> dict:
    d = os.path.join(vault or VAULT, "desk")
    return {"dir": d, "settings": os.path.join(d, "settings.json"), "outbox": os.path.join(d, "outbox.jsonl"),
            "state": os.path.join(d, "state.json"), "lock": os.path.join(d, ".lock")}


def _load(path: str, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return copy.deepcopy(default)


def _save(path: str, value) -> None:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".new"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(value, fh, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _int(x, lo: int, hi: int, default: int) -> int:
    return min(hi, max(lo, int(round(x)))) if isinstance(x, (int, float)) and not isinstance(x, bool) else default


def merged(raw) -> dict:
    """The website's settings made whole: anything missing or odd takes today's value. The website checks them
    too (mergeSettings); this keeps Val safe from a hand-edited file."""
    s = copy.deepcopy(DEFAULTS)
    r = raw if isinstance(raw, dict) else {}
    for k in ("paused", "autoSend"):
        if isinstance(r.get(k), bool):
            s[k] = r[k]
    for p in PROGRAMS:
        if isinstance((r.get("programs") or {}).get(p), bool):
            s["programs"][p] = r["programs"][p]
    s["answers"] = {k: v for k, v in (r.get("answers") or {}).items() if isinstance(k, str) and isinstance(v, str)}
    links = r.get("links") or {}
    s["links"] = {"reviewLink": links.get("reviewLink") if isinstance(links.get("reviewLink"), str) else "",
                  "referralReward": links.get("referralReward") if isinstance(links.get("referralReward"), str) else ""}
    t = r.get("timing") or {}
    s["timing"] = {"recordingWaitMinutes": _int(t.get("recordingWaitMinutes"), 0, 240, 120),
                   "callbackFrom": _int(t.get("callbackFrom"), 8, 19, 9),
                   "callbackTo": 19,
                   "callbackSaturday": t["callbackSaturday"] if isinstance(t.get("callbackSaturday"), bool) else True}
    lo = s["timing"]["callbackFrom"] + 1
    s["timing"]["callbackTo"] = _int(t.get("callbackTo"), lo, 20, max(lo, 19))
    for k in ALERT_KINDS:
        if (r.get("alerts") or {}).get(k) in ROUTES:
            s["alerts"][k] = r["alerts"][k]
    f = r.get("followups") or {}
    given = {t.get("key"): t for t in (f.get("touches") or []) if isinstance(t, dict)}
    touches, last = [], 0
    for key, days in TOUCHES:
        t = given.get(key) or {}
        d = _int(t.get("days"), last + 1, 365, max(days, last + 1))
        touches.append({"key": key, "days": d, "on": t["on"] if isinstance(t.get("on"), bool) else True,
                        "send": t.get("send") if t.get("send") in ("both", "text", "email") else "both"})
        last = d
    s["followups"] = {"touches": touches, "quietDays": _int(f.get("quietDays"), 1, 14, 3),
                      "listAt": f["listAt"] if isinstance(f.get("listAt"), str)
                      and re.match(r"^(0[6-9]|1[01]):[0-5]\d$", f["listAt"]) else "08:01"}
    return s


def settings(vault: Optional[str] = None) -> dict:
    """Val's settings as the website last said them, or today's values when it never has."""
    saved = _load(paths(vault)["settings"], {})
    return merged(saved.get("settings") if isinstance(saved, dict) else None)


def program_on(name: str, vault: Optional[str] = None) -> bool:
    try:
        return bool(settings(vault)["programs"].get(name, True))
    except Exception:   # never stop a program because the settings can't be read
        return True


def alert_route(kind: str, vault: Optional[str] = None) -> str:
    try:
        return settings(vault)["alerts"].get(kind if kind in ALERT_KINDS else "note", "both")
    except Exception:
        return "both"


def telegram_ok(kind: str, vault: Optional[str] = None) -> bool:
    """Does this kind of note go to Telegram? Telegram stays on unless Gerrit chose iPad only or neither."""
    return alert_route(kind, vault) in ("both", "telegram")


def followup_rules(vault: Optional[str] = None) -> dict:
    """The follow-up rules from Settings > Follow-up rules:
    {"touches": [(key, timedelta, send)] only the ones that are on, "quiet": timedelta, "list_at": time,
     "plan_at": time (20 minutes before)}. "48 hours" stays 48 hours while it is 2 days."""
    f = settings(vault)["followups"]
    touches = []
    for t in f["touches"]:
        if t["on"]:
            off = timedelta(hours=48) if t["key"] == "48 hours" and t["days"] == 2 else timedelta(days=t["days"])
            touches.append((t["key"], off, t["send"]))
    h, m = (int(x) for x in f["listAt"].split(":"))
    list_at = time(h, m)
    plan = datetime(2000, 1, 1, h, m) - timedelta(minutes=20)
    return {"touches": touches, "quiet": timedelta(days=f["quietDays"]), "list_at": list_at, "plan_at": plan.time(),
            "send": {t["key"]: t["send"] for t in f["touches"]}}


def recording_wait(vault: Optional[str] = None) -> timedelta:
    return timedelta(minutes=settings(vault)["timing"]["recordingWaitMinutes"])


def callback_hours(vault: Optional[str] = None) -> Tuple[time, time, frozenset]:
    """(first call-back, last call-back, work days) for the missed-call text-back."""
    t = settings(vault)["timing"]
    days = frozenset({0, 1, 2, 3, 4, 5} if t["callbackSaturday"] else {0, 1, 2, 3, 4})
    return time(t["callbackFrom"], 0), time(t["callbackTo"], 0), days


# ------------------------------------------------------------------ the outbox (her programs never wait)

@contextmanager
def _locked(vault: Optional[str] = None):
    p = paths(vault)
    os.makedirs(p["dir"], mode=0o700, exist_ok=True)
    with open(p["lock"], "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield p
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def _add(entry: dict, vault: Optional[str] = None) -> bool:
    try:
        with _locked(vault) as p:
            with open(p["outbox"], "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
            os.chmod(p["outbox"], 0o600)
        return True
    except Exception:   # a note never stops the program that sends it
        return False


def note(kind: str, text: str, link: Optional[str] = None, vault: Optional[str] = None) -> bool:
    """A copy of what Val told Gerrit, for From Val (and an iPad alert when that kind goes there)."""
    text = (text or "").strip()
    if not text:
        return False
    kind = kind if kind in ALERT_KINDS else "note"
    at = iso(_now())
    entry = {"op": "note", "note": {"id": f"{kind}:{at}:{short_hash(text)}", "kind": kind, "text": text[:4000],
                                     "at": at}}
    if link:
        entry["note"]["link"] = link
    return _add(entry, vault)


def question_id(kind: str, ref: str) -> str:
    """The same question about the same thing has the same id, so asking twice makes one card."""
    return f"{kind}:{short_hash(ref)}"


def ask(qid: str, kind: str, question: str, options: Optional[List[dict]] = None, allow_text: bool = False,
        customer: str = "", link: str = "", meta: Optional[dict] = None, vault: Optional[str] = None) -> bool:
    """A question card on Needs you. meta stays on Val's computer (what to do with the answer)."""
    q = {"id": qid, "kind": kind, "question": question[:1200], "options": list(options or [])[:4],
         "allowText": bool(allow_text)}
    if customer:
        q["customer"] = customer[:80]
    if link:
        q["link"] = link
    return _add({"op": "ask", "question": q, "meta": meta or {}}, vault)


def close(qid: str, note_text: str = "Done.", vault: Optional[str] = None) -> bool:
    return _add({"op": "close", "id": qid, "note": note_text[:200]}, vault)


def take_outbox(vault: Optional[str] = None) -> List[dict]:
    with _locked(vault) as p:
        try:
            with open(p["outbox"], encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            return []
    out = []
    for row in lines:
        try:
            e = json.loads(row)
        except ValueError:
            continue
        if isinstance(e, dict) and e.get("op"):
            out.append(e)
    return out


def keep_outbox(left: List[dict], sent: int, vault: Optional[str] = None) -> None:
    """Takes the first `sent` lines out (more may have been added meanwhile) and keeps the rest, at most
    OUTBOX_MAX, dropping the oldest notes first."""
    with _locked(vault) as p:
        try:
            with open(p["outbox"], encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            lines = []
        rest = lines[sent:]
        while len(rest) > OUTBOX_MAX:
            idx = next((i for i, r in enumerate(rest) if '"op": "note"' in r), 0)
            rest.pop(idx)
        tmp = p["outbox"] + ".new"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.writelines(rest)
        os.chmod(tmp, 0o600)
        os.replace(tmp, p["outbox"])


# ------------------------------------------------------------------ the website

class Site:
    def __init__(self, website):
        self.w = website

    @classmethod
    def from_settings(cls) -> Optional["Site"]:
        import zingas_os as zo
        w = zo.Website.from_settings()
        return cls(w) if w else None

    def get(self) -> dict:
        return self.w.get(DOOR, {})

    def post(self, body: dict) -> dict:
        return self.w.post(DOOR, body)[1]


# ------------------------------------------------------------------ Hermes (Val herself)

def _hermes(args: List[str], stdin: Optional[str] = None, timeout: int = 60) -> str:
    out = subprocess.run(["hermes"] + args, input=stdin, capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"hermes {args[0]} exited {out.returncode}")
    return out.stdout


class Hermes:
    """The few Hermes commands the desk uses. Tests give a fake."""

    def sessions(self, source: str, limit: int) -> List[Tuple[str, str]]:
        """[(title, id)], newest first."""
        text = _hermes(["sessions", "list", "--source", source, "--limit", str(limit)])
        rows = []
        for row in text.splitlines():
            parts = row.split()
            if len(parts) >= 2 and re.match(r"^[A-Za-z0-9_][A-Za-z0-9_.:-]{5,79}$", parts[-1]) \
                    and re.search(r"\d{8}_\d{6}", parts[-1]):
                rows.append((row.strip(), parts[-1]))
        return rows

    def messages(self, session_id: str) -> List[dict]:
        text = _hermes(["sessions", "export", "-", "--format", "jsonl", "--session-id", session_id], timeout=90)
        out = []
        for row in text.splitlines():
            try:
                s = json.loads(row)
            except ValueError:
                continue
            if isinstance(s, dict) and isinstance(s.get("messages"), list):
                out += [m for m in s["messages"] if isinstance(m, dict)]
        return out

    def chat(self, text: str, session_id: str = "") -> str:
        args = ["chat", "-q", text, "-Q", "--source", "telegram"]
        if session_id:
            args += ["--resume", session_id]
        return _hermes(args, timeout=CHAT_TIMEOUT).strip()

    def send(self, text: str) -> None:
        _hermes(["send", "--to", "telegram", "--quiet", "--file", "-"], stdin=text)

    def status(self) -> str:
        out = subprocess.run(["supervisorctl", "status"], capture_output=True, text=True, timeout=30)
        return out.stdout


def content_of(m: dict) -> str:
    c = m.get("content")
    if isinstance(c, str):
        return c.strip()
    if isinstance(c, list):
        return "\n".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text").strip()
    return ""


def _at(ts) -> str:
    try:
        return iso(datetime.fromtimestamp(float(ts), timezone.utc))
    except (TypeError, ValueError, OverflowError, OSError):
        return iso(_now())


def programs_of(status_text: str) -> List[dict]:
    """supervisorctl status as [{name, state}] (no customer data in it)."""
    out = []
    for row in status_text.splitlines():
        parts = row.split()
        if len(parts) >= 2 and parts[1].isupper():
            name = re.sub(r"[^a-z0-9_-]", "-", parts[0].lower().split(":")[-1])[:40]
            if name:
                out.append({"name": name, "state": parts[1].lower()[:20]})
    return out


# ------------------------------------------------------------------ the desk

def log(text: str) -> None:
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {text}", flush=True)


class Desk:
    def __init__(self, site: Site, hermes: Optional[Hermes] = None, vault: Optional[str] = None,
                 clock: Callable[[], datetime] = _now):
        self.site, self.hermes, self.vault, self.clock = site, hermes or Hermes(), vault or VAULT, clock
        self.p = paths(self.vault)
        self.st = _load(self.p["state"], {})
        for k, v in (("asked", {}), ("mirror", {}), ("injected", []), ("briefs", []), ("applied", {})):
            self.st.setdefault(k, copy.deepcopy(v))

    def save(self) -> None:
        self.st["injected"] = self.st["injected"][-200:]
        self.st["briefs"] = self.st["briefs"][-60:]
        _save(self.p["state"], self.st)

    # one look ---------------------------------------------------------
    def step(self) -> dict:
        did = {"sent": self.flush()}
        answer = self.site.get()
        self.take_settings(answer)
        if not self.st.get("seeded"):
            self.seed()
        did["answers"] = self.answers(answer.get("answers") or [])
        did["closed"] = self.close_done_elsewhere()
        msgs = [m for m in (answer.get("messages") or []) if isinstance(m, dict) and m.get("id")]
        if msgs:
            did["messages"] = self.message(msgs[0])
        now = self.clock()
        if self._due("last_mirror", MIRROR_EVERY, now):
            did["turns"] = self.mirror()
        if self._due("last_slow", SLOW_EVERY, now):
            did["briefs"] = self.briefs()
            self.health()
        did["sent"] += self.flush()
        self.save()
        return did

    def _due(self, key: str, every: timedelta, now: datetime) -> bool:
        last = self.st.get(key)
        try:
            due = not last or now - datetime.fromisoformat(last.replace("Z", "+00:00")) >= every
        except ValueError:
            due = True
        if due:
            self.st[key] = iso(now)
        return due

    # the outbox -------------------------------------------------------
    def flush(self) -> int:
        """Sends what Val's programs added. Stops at the first failure and keeps the rest for next time."""
        entries = take_outbox(self.vault)
        sent = 0
        i = 0
        while i < len(entries):
            e = entries[i]
            if e["op"] == "note":
                batch = []
                while i + len(batch) < len(entries) and entries[i + len(batch)]["op"] == "note" and len(batch) < 50:
                    batch.append(entries[i + len(batch)]["note"])
                body = {"op": "note", "notes": batch}
                n = len(batch)
            elif e["op"] == "ask":
                body, n = {"op": "ask", "question": e["question"]}, 1
            elif e["op"] == "close":
                body, n = {"op": "close", "id": e["id"], "note": e.get("note") or "Done."}, 1
            else:
                i += 1
                sent += 1
                continue
            try:
                self.site.post(body)
            except Exception as ex:
                status = getattr(ex, "status", 0)
                if status == 400:   # the website will never take it: drop it, keep the rest moving
                    log(f"desk: the website refused one {e['op']} (400)")
                else:
                    log(f"desk: outbox waits ({type(ex).__name__} {status or ''})".rstrip())
                    break
            if e["op"] == "ask":
                q = e["question"]
                self.st["asked"][q["id"]] = {"kind": q["kind"], "question": q["question"],
                                              "options": q.get("options") or [], "meta": e.get("meta") or {},
                                              "at": iso(self.clock())}
            if e["op"] == "close":
                self.st["asked"].pop(e["id"], None)
            i += n
            sent += n
        if sent:
            keep_outbox([], sent, self.vault)
            self.save()
        return sent

    # settings ---------------------------------------------------------
    def take_settings(self, answer: dict) -> bool:
        version = answer.get("version")
        if not isinstance(answer.get("settings"), dict) or not isinstance(version, int):
            return False
        saved = _load(self.p["settings"], {})
        if saved.get("version") == version:
            return False
        s = merged(answer["settings"])
        _save(self.p["settings"], {"version": version, "settings": s, "at": iso(self.clock())})
        self.apply_answers(s)
        self.apply_links(s)
        log(f"desk: settings version {version}")
        return True

    def apply_answers(self, s: dict) -> None:
        """Writes the answers Gerrit changed on the website into Val's value-answers.md. A topic he changed in
        Telegram since is left alone unless he changes that same topic on the website."""
        import value_answers as va
        applied = self.st["applied"].setdefault("answers", {})
        local = va.load(self.vault)
        changed = False
        for topic, text in s["answers"].items():
            text = text.strip()
            last = applied.get(topic)
            if text == last:
                continue
            applied[topic] = text
            if text and local.get(topic, "").strip() != text and va.check_answer(text) is None:
                local[topic] = text
                changed = True
            elif not text and last and topic in local:
                local.pop(topic)
                changed = True
        if changed:
            va.save(local, self.vault)

    def apply_links(self, s: dict) -> None:
        import zingas_installs as zi
        applied = self.st["applied"].setdefault("links", {})
        cfg = zi.settings(self.vault)
        changed = False
        for key, local_key in (("reviewLink", "review_link"), ("referralReward", "referral")):
            value = (s["links"].get(key) or "").strip()
            last = applied.get(key)
            if value == last:
                continue
            applied[key] = value
            ok = (zi.LINK_RE.match(value) if key == "reviewLink" else not zi.PRICE.search(value)) if value else True
            if value and ok and cfg.get(local_key) != value:
                cfg[local_key] = value[:200] if key == "referralReward" else value
                changed = True
            elif not value and last and cfg.get(local_key):
                cfg.pop(local_key)
                changed = True
        if changed:
            zi.save_settings(cfg, self.vault)

    def seed(self) -> None:
        """First sync: Val's own saved answers and links fill the website's empty ones."""
        try:
            import value_answers as va
            import zingas_installs as zi
            cfg = zi.settings(self.vault)
            self.site.post({"op": "seed", "answers": va.load(self.vault),
                            "links": {"reviewLink": cfg.get("review_link") or "",
                                      "referralReward": cfg.get("referral") or ""}})
            self.st["seeded"] = iso(self.clock())
        except Exception as e:
            log(f"desk: seed waits ({type(e).__name__})")

    # Gerrit's answers -------------------------------------------------
    def answers(self, answers: List[dict]) -> int:
        done = 0
        for a in answers:
            qid = a.get("id")
            if not isinstance(qid, str):
                continue
            asked = self.st["asked"].get(qid) or {}
            kind = a.get("kind") or asked.get("kind") or ""
            try:
                if kind == "related_done":
                    note_text = self.related_answer(asked, a.get("answer") or "")
                else:
                    note_text = self.generic_answer(asked, a)
            except Exception as e:
                tries = self.st.setdefault("tries", {})
                tries[qid] = tries.get(qid, 0) + 1
                log(f"desk: answer not made ({type(e).__name__}), try {tries[qid]}")
                if tries[qid] < 3:
                    continue
                note_text = "Val couldn't take this answer. Tell her in Telegram."
            self.st.get("tries", {}).pop(qid, None)
            self.site.post({"op": "taken", "answers": [qid]})
            self.site.post({"op": "close", "id": qid, "note": note_text})
            self.st["asked"].pop(qid, None)
            done += 1
        return done

    def related_answer(self, asked: dict, answer: str) -> str:
        """Yes: the tasks are marked done, the same as "done 4" in Telegram. No: nothing changes."""
        import zingas_todo as zt
        ids = [i for i in (asked.get("meta") or {}).get("ids", []) if isinstance(i, str)]
        if answer != "yes" or not ids:
            return "Left open."
        todo = zt.TodoList(self.vault)
        closed = [c for c in (todo.close_id(i) for i in ids) if c]
        if not closed:
            return "Those tasks were already closed."
        zt.after_done(todo, closed)
        zt.tell_gerrit("✅ Done, from the website:\n" + "\n".join(f"- {c['task']}" for c in closed), "note")
        return "Marked done." if len(closed) == 1 else f"Marked {len(closed)} tasks done."

    def generic_answer(self, asked: dict, a: dict) -> str:
        """Val gets the answer in her conversation, the same as if Gerrit had typed it in Telegram."""
        label = (a.get("label") or a.get("answer") or "").strip()
        question = asked.get("question") or "your question"
        reply = self.talk(f'Gerrit answered your question on the website. Your question: "{question}"\n'
                          f"His answer: {label}", shown=f"Your answer to Val's question: {label}")
        return "Val has your answer." if reply is not None else "Val got your answer."

    def close_done_elsewhere(self) -> int:
        """A "done 4" in Telegram answers the same card: it closes when none of its tasks is still open."""
        related = {q: a for q, a in self.st["asked"].items() if a.get("kind") == "related_done"}
        if not related:
            return 0
        import zingas_todo as zt
        open_ids = {i["id"] for i in zt.TodoList(self.vault).open_items()}
        n = 0
        for qid, a in related.items():
            ids = (a.get("meta") or {}).get("ids") or []
            if ids and not any(i in open_ids for i in ids):
                close(qid, "Done in Telegram.", self.vault)
                n += 1
        return n

    # Talk to Val ------------------------------------------------------
    def talk(self, text: str, shown: str) -> Optional[str]:
        """One turn in Val's Telegram conversation from the website. Her answer goes to Telegram (with what
        Gerrit said, so both places hold the whole conversation) and to the website. None when she couldn't."""
        sessions = self.hermes.sessions("telegram", 1)
        sid = sessions[0][1] if sessions else ""
        prompt = WEB_MARK + text
        self.st["injected"].append(short_hash(prompt))
        reply = self.hermes.chat(prompt, sid)
        if not reply:
            return None
        self.st["injected"].append(short_hash(reply))
        try:
            self.hermes.send(f"{COPY_MARK} {shown}\n\n{reply}")
        except Exception as e:
            log(f"desk: Telegram copy not sent ({type(e).__name__})")
        now = iso(self.clock())
        self.site.post({"op": "turns", "turns": [{"id": f"web:{short_hash(now + reply)}", "author": "val",
                                                   "channel": "web", "text": reply[:4000], "at": now}]})
        return reply

    def message(self, m: dict) -> bool:
        """One website message from Gerrit (Talk to Val)."""
        self.site.post({"op": "taken", "messages": [m["id"]]})
        text = str(m.get("text") or "").strip()[:4000]
        try:
            reply = self.talk(f"Gerrit wrote on the website: {text}", shown=text)
        except Exception as e:
            log(f"desk: website message not answered ({type(e).__name__})")
            reply = None
            problem = "Val couldn't answer just now. Try again in a minute, or text her in Telegram."
        else:
            problem = "" if reply else "Val had no answer. Try again, or text her in Telegram."
        self.site.post({"op": "replied", "results": [{"id": m["id"], "ok": bool(reply), "message": problem}]})
        return bool(reply)

    def mirror(self) -> int:
        """Copies the Telegram conversation's new turns to the website (not the ones the website started)."""
        try:
            sessions = self.hermes.sessions("telegram", 2)
        except Exception as e:
            log(f"desk: Telegram turns not read ({type(e).__name__})")
            return 0
        turns = []
        injected = set(self.st["injected"])
        for _, sid in reversed(sessions):
            try:
                msgs = self.hermes.messages(sid)
            except Exception:
                continue
            last = self.st["mirror"].get(sid)
            fresh = [m for m in msgs if m.get("role") in ("user", "assistant") and isinstance(m.get("id"), int)
                     and (last is None or m["id"] > last)]
            if last is None:
                fresh = fresh[-FIRST_MIRROR:]
            for m in fresh:
                text = content_of(m)
                if not text or text.startswith((WEB_MARK, COPY_MARK)) or short_hash(text) in injected:
                    continue
                turns.append({"id": f"tg:{sid}:{m['id']}"[:80], "author": "gerrit" if m["role"] == "user" else "val",
                              "channel": "telegram", "text": text[:4000], "at": _at(m.get("timestamp"))})
            ids = [m["id"] for m in msgs if isinstance(m.get("id"), int)]
            if ids:
                self.st["mirror"][sid] = max(ids)
        for k in [k for k in self.st["mirror"] if k not in {s for _, s in sessions}][:-5]:
            self.st["mirror"].pop(k)
        for i in range(0, len(turns), 200):
            self.site.post({"op": "turns", "turns": turns[i:i + 200]})
        return len(turns)

    # briefs and health ------------------------------------------------
    def briefs(self) -> int:
        try:
            rows = self.hermes.sessions("cron", 4)
        except Exception:
            return 0
        n = 0
        for title, sid in rows:
            kind = "morning" if "morning-brief" in title else "evening" if "evening-brief" in title else ""
            if not kind or sid in self.st["briefs"]:
                continue
            msgs = self.hermes.messages(sid)
            said = [m for m in msgs if m.get("role") == "assistant" and content_of(m)]
            if not said:
                continue   # still being written; next look
            day = re.search(r"_(\d{4})(\d{2})(\d{2})_", sid)
            self.site.post({"op": "brief", "brief": {
                "id": f"{kind}:{sid}"[:80], "kind": kind, "text": content_of(said[-1])[:12000],
                "day": f"{day.group(1)}-{day.group(2)}-{day.group(3)}" if day else iso(self.clock())[:10],
                "at": _at(said[-1].get("timestamp"))}})
            self.st["briefs"].append(sid)
            n += 1
        return n

    def health(self) -> None:
        try:
            programs = programs_of(self.hermes.status())
        except Exception as e:
            programs = []
            log(f"desk: supervisor not read ({type(e).__name__})")
        try:
            self.site.post({"op": "health", "health": {"at": iso(self.clock()), "programs": programs,
                                                       "note": "" if programs else "Val couldn't read her programs."}})
        except Exception as e:
            log(f"desk: health not sent ({type(e).__name__})")


def run(vault: Optional[str] = None) -> None:   # pragma: no cover (a loop; Desk.step is tested)
    site = None
    while site is None:
        site = Site.from_settings()
        if site is None:
            log("desk: the website key or address is not set up (1Password: ZINGAS_OS_URL, ASSISTANT_API_TOKEN)")
            _time.sleep(300)
    desk = Desk(site, vault=vault)
    while True:
        try:
            did = desk.step()
            busy = {k: v for k, v in did.items() if v}
            if busy:
                log("desk: " + ", ".join(f"{k} {v}" for k, v in busy.items()))
        except Exception as e:   # the website away: try again shortly
            status = getattr(e, "status", "")
            log(f"desk: {type(e).__name__} {status}".rstrip())
            _time.sleep(30)
        _time.sleep(EVERY)


# ------------------------------------------------------------------ the CLI

def _read_text(arg: str) -> str:
    return sys.stdin.read() if arg == "-" else open(arg, encoding="utf-8").read()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="zingas-desk", description="Val's desk on the website.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    a = sub.add_parser("ask")
    a.add_argument("--id", required=True)
    a.add_argument("--kind", required=True)
    a.add_argument("--question-file", required=True)
    a.add_argument("--option", action="append", default=[], help="key=Label, up to 4")
    a.add_argument("--text", action="store_true", help="Gerrit may type an answer")
    a.add_argument("--customer", default="")
    c = sub.add_parser("close")
    c.add_argument("--id", required=True)
    c.add_argument("--note", default="Done.")
    n = sub.add_parser("note")
    n.add_argument("--kind", default="note")
    n.add_argument("--text-file", required=True)
    sub.add_parser("settings")
    sub.add_parser("check")
    args = p.parse_args(argv)

    if args.cmd == "run":
        run()
        return 0
    if args.cmd == "ask":
        options = []
        for o in args.option[:4]:
            key, _, label = o.partition("=")
            if not re.match(r"^[A-Za-z0-9_-]{1,40}$", key) or not label.strip():
                print("Each --option is key=Label (key: letters, digits, _ or -).")
                return 2
            options.append({"key": key, "label": label.strip()[:60]})
        if not options and not args.text:
            print("A question needs --option buttons or --text.")
            return 2
        if not re.match(r"^[A-Za-z0-9_:.-]{1,80}$", args.id) or not re.match(r"^[a-z_]{1,40}$", args.kind):
            print("--id is letters, digits or _:.- ; --kind is lowercase words with _.")
            return 2
        question = _read_text(args.question_file).strip()
        if not question:
            print("The question is empty.")
            return 2
        ok = ask(args.id, args.kind, question, options, args.text, args.customer)
        print("On the website's Needs you list within a few seconds." if ok else "Couldn't save the question.")
        return 0 if ok else 1
    if args.cmd == "close":
        return 0 if close(args.id, args.note) else 1
    if args.cmd == "note":
        return 0 if note(args.kind, _read_text(args.text_file)) else 1
    if args.cmd == "settings":
        s = settings()
        saved = _load(paths()["settings"], {})
        s.pop("answers", None)
        print(json.dumps({"version": saved.get("version"), "settings": s}, indent=1))
        return 0
    if args.cmd == "check":
        site = Site.from_settings()
        if site is None:
            print("Not set up: ZINGAS_OS_URL or ASSISTANT_API_TOKEN is missing.")
            return 1
        try:
            answer = site.get()
        except Exception as e:
            print(f"The desk did not answer ({getattr(e, 'status', '') or type(e).__name__}).")
            return 1
        print(f"The desk answered: settings version {answer.get('version')}, "
              f"{len(answer.get('answers') or [])} answer(s), {len(answer.get('messages') or [])} message(s) waiting.")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
