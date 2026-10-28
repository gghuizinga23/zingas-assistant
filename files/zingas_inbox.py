#!/usr/bin/env python3
"""zingas-inbox: new work email becomes to-do list tasks. Plain code, no AI of its own.

Runs on Val's computer under supervisord. Every 2 minutes it asks Val's locked
Gmail link (Composio, read and draft only) for mail that came in since the last
look, in every label and folder. Then:
  1. Drops promotions, social, spam and no-reply senders without asking anyone.
  2. Opens each remaining email and asks Val, in one run with no real tools,
     whether it puts something on Gerrit's to-do list and how important it is.
     Email text is data: the run can't send, forward or delete anything.
  3. Adds the tasks itself (zingas_todo) and tells Gerrit in Val's Telegram
     chat right away, any hour (Gerrit's rule for to-do alerts).
  4. An email from a known customer (their address is in their customer file, or
     on the quote follow-up list) gets a line in that customer's timeline, and Val
     reads the customer's file while she judges it. Gerrit's own sent emails to a
     known customer get a line too (zingas_customer, docs/VAL-BRAIN.md Part 1).
  5. A sent email in the thread of a Gmail draft Val made is handed to zingas_voice,
     which saves Val's draft beside what Gerrit sent, so Val learns from his changes.

The first run only notes what is already there, so old mail never floods the list.
It never prints email text to its log: counts and ids only.

  zingas-inbox run      the loop (supervisord runs it)
  zingas-inbox check    one look; prints counts only, changes nothing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Callable, List, Optional

sys.path.insert(0, "/usr/local/lib/zingas")
sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))
import zingas_customer as zc  # noqa: E402
import zingas_todo as zt  # noqa: E402
try:
    import zingas_voice as zv  # noqa: E402
except ImportError:      # an older install without it: the inbox still works
    zv = None

HERMES_HOME = os.environ.get("HERMES_HOME", "/root/.hermes")
ENV = os.path.join(HERMES_HOME, ".env")
OP_ENV = os.path.join(HERMES_HOME, ".op.env")
STATE = os.path.join(HERMES_HOME, "inbox-state.json")
KEY_REF = "op://Zingas Assistant/Assistant Secrets/COMPOSIO_VAL_KEY"
EVERY = 120                # seconds between looks
BATCH = 8                  # emails judged in one Val run
MAX_TRIES = 3
TEXT_LIMIT = 3000
QUERY = "-in:sent -in:drafts -in:chats -in:spam -in:trash -category:promotions -category:social -category:forums"
SKIP_LABELS = {"SPAM", "TRASH", "DRAFT", "SENT", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS"}
NO_REPLY = re.compile(r"no-?reply|do-?not-?reply|mailer-daemon|postmaster|notifications?@|bounce", re.I)


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}", flush=True)


def env_value(path: str, name: str) -> str:
    try:
        with open(path) as fh:
            for row in fh:
                if row.startswith(name + "="):
                    return row.strip().split("=", 1)[1]
    except OSError:
        pass
    return ""


# ------------------------------------------------------------ Gmail (Composio)

class GmailError(RuntimeError):
    pass


class Gmail:
    """Val's locked Composio session over MCP. Only read and draft tools exist in it."""

    def __init__(self, url: str, key: str, timeout: float = 90.0):
        if not url.startswith("https://"):
            raise ValueError("COMPOSIO_MAIL_MCP_URL must start with https://")
        self.url, self.key, self.timeout = url, key, timeout
        self.session: Optional[str] = None
        self.n = 0

    def _rpc(self, method: str, params=None, notify: bool = False):
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            self.n += 1
            msg["id"] = self.n
        headers = {"x-api-key": self.key, "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self.session:
            headers["mcp-session-id"] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(msg).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self.session = self.session or r.headers.get("mcp-session-id")
                text = r.read().decode(errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (400, 404) and self.session:
                self.session = None          # the session expired; open a new one next time
            raise GmailError(f"Gmail link HTTP {e.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise GmailError(f"can't reach the Gmail link ({type(e).__name__})") from None
        if notify:
            return None
        for row in text.splitlines():        # answers may come as server-sent events
            if row.startswith("data:"):
                text = row[5:].strip()
        try:
            return json.loads(text)
        except ValueError:
            raise GmailError("Gmail link sent something that isn't JSON") from None

    def _open(self) -> None:
        if not self.session:
            self._rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                     "clientInfo": {"name": "zingas-inbox", "version": "1"}})
            self._rpc("notifications/initialized", notify=True)

    def call(self, tool: str, args: dict) -> dict:
        self._open()
        out = self._rpc("tools/call", {"name": tool, "arguments": args})
        if "error" in out:
            self.session = None
            raise GmailError(f"{tool} refused")
        res = out.get("result") or {}
        text = " ".join(c.get("text", "") for c in res.get("content", []) if isinstance(c, dict))
        try:
            data = json.loads(text)
        except ValueError:
            raise GmailError(f"{tool} answer isn't JSON") from None
        if res.get("isError") or (isinstance(data, dict) and data.get("successful") is False):
            raise GmailError(f"{tool} didn't work")
        return (data.get("data") or {}) if isinstance(data, dict) else {}

    def sent(self, after_epoch: int, limit: int = 25) -> List[dict]:
        """Gerrit's own sent mail since then (for the customer timelines)."""
        data = self.call("GMAIL_FETCH_EMAILS", {"query": f"in:sent after:{int(after_epoch)}",
                                                "max_results": limit, "verbose": False,
                                                "include_payload": False, "include_spam_trash": False})
        return list(data.get("messages") or [])

    def recent(self, after_epoch: int, limit: int = 25) -> List[dict]:
        data = self.call("GMAIL_FETCH_EMAILS", {"query": f"{QUERY} after:{int(after_epoch)}",
                                                "max_results": limit, "verbose": False,
                                                "include_payload": False, "include_spam_trash": False})
        return list(data.get("messages") or [])

    def body(self, message_id: str) -> str:
        data = self.call("GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID", {"message_id": message_id, "format": "full"})
        text = data.get("messageText") or (data.get("preview") or {}).get("body") or ""
        return str(text)[:TEXT_LIMIT]


def connect() -> Gmail:
    url = env_value(ENV, "COMPOSIO_MAIL_MCP_URL")
    key = os.environ.get("COMPOSIO_VAL_KEY", "")
    if not key:
        token = env_value(OP_ENV, "OP_SERVICE_ACCOUNT_TOKEN")
        if token:
            out = subprocess.run(["op", "read", KEY_REF], capture_output=True, text=True, timeout=30,
                                 env=dict(os.environ, OP_SERVICE_ACCOUNT_TOKEN=token))
            key = out.stdout.strip() if out.returncode == 0 else ""
    if not url or not key:
        raise GmailError("Val's Gmail link or key isn't set up")
    return Gmail(url, key)


# ------------------------------------------------------------------ the work

def label_of(msg: dict) -> str:
    """The user label to mention, if the email isn't simply in the inbox."""
    labels = [x for x in msg.get("labelIds") or [] if not x.startswith("CATEGORY_")
              and x not in ("INBOX", "UNREAD", "IMPORTANT", "STARRED")]
    return "" if "INBOX" in (msg.get("labelIds") or []) and not labels else ", ".join(labels)


def preview_of(msg: dict) -> str:
    p = msg.get("preview")
    return str((p.get("body") if isinstance(p, dict) else p) or "")[:TEXT_LIMIT]


def name_of(sender: str) -> str:
    """'Pat Lee <pat@x.com>' -> 'Pat Lee'; a bare address stays as it is."""
    m = re.match(r'\s*"?([^"<]+?)"?\s*<[^>]+>', sender or "")
    return (m.group(1) if m else sender or "").strip()[:80]


INTERNAL = ("@zingashome.com", "@zingas.com")


def address_of(sender: str) -> str:
    """The customer's email address in a From or To line; "" for none or for Zinga's own people."""
    m = zc.EMAIL_RE.search(sender or "")
    address = m.group(0).lower() if m else ""
    return "" if address.endswith(INTERNAL) else address


def worth_a_look(msg: dict) -> bool:
    if set(msg.get("labelIds") or []) & SKIP_LABELS:
        return False
    return not NO_REPLY.search(str(msg.get("sender") or ""))


class Inbox:
    def __init__(self, gmail, todo: Optional[zt.TodoList] = None, ask_val: Callable[[str], str] = zt.run_val,
                 notify: Callable[[str], None] = zt.teller("new_task"), state_path: str = STATE,
                 clock: Callable[[], float] = time.time, skill_path: str = zt.SKILL, vault: str = ""):
        self.gmail, self.todo = gmail, todo or zt.TodoList()
        self.ask_val, self.notify, self.state_path, self.clock = ask_val, notify, state_path, clock
        self.skill_path = skill_path
        self.vault = vault or os.path.dirname(self.todo.folder)     # the vault the to-do list lives in

    def _state(self) -> dict:
        try:
            with open(self.state_path) as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def _save(self, st: dict) -> None:
        st["seen"] = st.get("seen", [])[-500:]
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(st, fh)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.state_path)

    def once(self) -> dict:
        st = self._state()
        now = int(self.clock())
        if "since" not in st:                        # first run: note what's there, add nothing
            msgs = self.gmail.recent(now - 3600)
            self._save({"since": now, "seen": [m["messageId"] for m in msgs if m.get("messageId")], "tries": {}})
            return {"baseline": len(msgs)}
        seen, tries = set(st.get("seen", [])), st.get("tries", {})
        msgs = [m for m in self.gmail.recent(st["since"] - 900) if m.get("messageId") not in seen]
        msgs.sort(key=lambda m: m.get("messageTimestamp") or "")
        done = {"new": len(msgs), "skipped": 0, "added": 0, "updated": 0, "retry": 0}
        look = []
        for m in msgs:
            if worth_a_look(m):
                look.append(m)
            else:
                st.setdefault("seen", []).append(m["messageId"])
                done["skipped"] += 1
        for k in range(0, len(look), BATCH):
            self._judge(look[k:k + BATCH], st, tries, done)
        self._sent_mail(st, now)
        if not done["retry"]:
            st["since"] = now
        st["tries"] = tries
        self._save(st)
        return done

    def _customer(self, address: str) -> str:
        try:
            return zc.resolve(email=address, vault=self.vault) if address else ""
        except Exception as e:
            log(f"customer file: {type(e).__name__}")
            return ""

    def _sent_mail(self, st: dict, now: int) -> None:
        """Gerrit's sent emails to known customers go in their timelines. Best effort: never stops the inbox."""
        if not hasattr(self.gmail, "sent"):
            return
        seen = set(st.get("sent_seen", []))
        try:
            msgs = self.gmail.sent(st.get("sent_since", now) - 900)
        except GmailError as e:
            log(f"sent mail: {e}")
            return
        new = []
        for m in msgs:
            mid = m.get("messageId")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            new.append(m)
            st.setdefault("sent_seen", []).append(mid)
            subject = zc.one_line(m.get("subject"), 160) or "(no subject)"
            for address in {address_of(a) for a in zc.EMAIL_RE.findall(str(m.get("to") or ""))} - {""}:
                key = self._customer(address)
                if key:
                    try:
                        zc.log(key, "email_out", m.get("messageTimestamp"),
                               f"Subject: {subject}\n{zc.one_line(preview_of(m), 300)}",
                               ref="gmail:" + mid, who="Gerrit", vault=self.vault)
                    except Exception as e:
                        log(f"customer file: {type(e).__name__}")
        if new and zv is not None:
            try:   # a sent email in the thread of a Gmail draft Val made: Val learns what Gerrit changed
                zv.match_sent(new, self.gmail.body, self.vault)
            except Exception as e:
                log(f"voice edits: {type(e).__name__}")
        st["sent_seen"] = st.get("sent_seen", [])[-500:]
        st["sent_since"] = now

    def _judge(self, msgs: List[dict], st: dict, tries: dict, done: dict) -> None:
        things = []
        for m in msgs:
            try:
                text = self.gmail.body(m["messageId"])
            except GmailError:
                text = preview_of(m)
            key = self._customer(address_of(str(m.get("sender") or "")))
            things.append({"id": m["messageId"], "kind": "email", "from": str(m.get("sender") or "")[:120],
                           "subject": str(m.get("subject") or "")[:200], "label": label_of(m),
                           "text": text or "(couldn't open the email; judge from the subject)",
                           "customer": key, "note": zc.context(key, self.vault, 2500) if key else ""})
        listed = self.todo.open_items()   # the list Val is shown; its numbers can move while she thinks
        try:
            got = zt.parse_judgement(self.ask_val(zt.judge_prompt(things, listed, self.skill_path)),
                                     [t["id"] for t in things])
        except Exception as e:
            log(f"Val's answer didn't work ({type(e).__name__})")
            got = {}
        added, emergency = [], False
        for m, t in zip(msgs, things):
            r = got.get(t["id"])
            if r is None:
                n = tries.get(t["id"], 0) + 1
                tries[t["id"]] = n
                if n < MAX_TRIES:
                    done["retry"] += 1
                    continue
                # never lose an email: a plain task Gerrit can sort out
                r = {"action": "add", "task": "Read this email: " + (t["subject"] or "(no subject)")[:120],
                     "priority": "today", "due": "", "why": "I could not make a decision about this email.", "who": t["from"],
                     "update_number": 0, "emergency": False}
            tries.pop(t["id"], None)
            st.setdefault("seen", []).append(t["id"])
            if t["customer"]:
                try:
                    zc.log(t["customer"], "email_in", m.get("messageTimestamp"),
                           (r.get("summary") if isinstance(r.get("summary"), str) and r.get("summary").strip()
                            else f"Subject: {t['subject']}\n{zc.one_line(t['text'], 300)}"),
                           ref="gmail:" + t["id"], who=name_of(t["from"]), vault=self.vault)
                    zc.add_facts(t["customer"], r.get("facts"),
                                 f"email {zc.short_date(datetime.now(zt.TZ))}", self.vault)
                except Exception as e:
                    log(f"customer file: {type(e).__name__}")
            before = {i["id"] for i in self.todo.open_items()}
            item = zt.apply_judgement(self.todo, {"from": name_of(t["from"]), "sender": t["from"],
                                                  "subject": t["subject"], "text": t["text"]}, r, "email",
                                      ref="gmail:" + str(m.get("threadId") or ""),
                                      link=str(m.get("display_url") or ""),
                                      received=m.get("messageTimestamp"), listed=listed)
            if not item:
                done["skipped"] += 1
                continue
            if item["id"] in before:
                done["updated"] += 1
            else:
                done["added"] += 1
                added.append(item)
            emergency = emergency or r.get("emergency")
        zt.announce(added, self.todo, self.notify, emergency=emergency)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="zingas-inbox")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("check")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        g = connect()
        msgs = g.recent(int(time.time()) - 3600)
        print(f"Gmail link works. Last hour: {len(msgs)} email(s), {sum(map(worth_a_look, msgs))} worth a look. "
              "(Nothing was changed.)")
        return 0

    inbox = None
    while True:
        try:
            if not zt.program_on("inbox"):   # switched off in Assistant > Settings
                time.sleep(EVERY)
                continue
            inbox = inbox or Inbox(connect())
            done = inbox.once()
            if any(done.values()):
                log(f"done {done}")
        except GmailError as e:
            log(f"gmail: {e}")
            inbox = None if "isn't set up" in str(e) else inbox
        except Exception as e:     # keep running; supervisord restarts us if we die anyway
            log(f"error: {type(e).__name__}")
        time.sleep(EVERY)


if __name__ == "__main__":
    sys.exit(main())
