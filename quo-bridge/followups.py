"""F0: quote follow-ups, the quo-bridge side.

Val's computer plans each day's follow-ups (a text and an email per touch) and
hands the list over with her drafts-only code. Here:
  - the list becomes one card in Val Approvals: Approve all, or Review one by one
  - an approved follow-up waits for its time, then sends: the text through Quo,
    the email through Gerrit's Gmail (Composio main key, only here)
  - right before each send: a customer who texted since the list was made is
    paused, not sent; do-not-contact is blocked; after 8 PM their time it waits
    for tomorrow's list
  - nothing approved by 8 PM (Gerrit's time) sends; it goes back on the next list

Val's code can add follow-ups to the list, pause them, and read text history.
It can never approve or send one.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import send_gate
from clients import EmailError, QuoError
from store import parse_time, utc_iso

Response = Tuple[int, dict]

MAX_ITEMS = 40
MAX_TEXT = 1600
MAX_EMAIL = 6000
MAX_SUBJECT = 200
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TOUCH_RE = re.compile(r"^[A-Za-z0-9 ]{1,24}$")
THREAD_RE = re.compile(r"^[A-Za-z0-9]{1,40}$")
OPEN = ("planned", "pending", "editing", "held", "failed")
GERRIT_TZ = ZoneInfo("America/Indiana/Indianapolis")
ICON = {"planned": "⏳", "pending": "👀", "editing": "✏️", "held": "⏰", "approving": "📤", "sending": "📤",
        "sent": "✅", "skipped": "✖️", "paused": "⏸", "expired": "⌛", "blocked": "⛔",
        "stopped_customer": "🛑", "failed": "⚠️"}


def followup_id(customer_key: str, touch: str, day: str) -> str:
    """One id per customer, touch and day's list, so a list sent twice never makes
    two, and a touch that was not approved can come back on a later day's list."""
    return "f" + hashlib.sha1(f"{customer_key}|{touch}|{day}".encode()).hexdigest()[:11]


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return GERRIT_TZ


def _when(dt: Optional[datetime], tz_name: str) -> str:
    return dt.astimezone(_tz(tz_name)).strftime("%a %-I:%M %p") if dt else "?"


def _pretty(phone: str) -> str:
    d = (phone or "")[-10:]
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else "no phone"


class FollowupMixin:
    """Mixed into Bridge. Uses self.store, self.quo, self.tg, self.email, self.now,
    self.cfg, self._tell_gerrit, self._edit_card, self._answer, self._log."""

    email = None   # ComposioGmail, or None until Gerrit sets up email sending

    # ------------------------------------------------------------ Val's doors

    def val_followups(self, payload: dict) -> Response:
        from bridge import us_phone   # bridge imports this module; import here to avoid a loop
        day = str(payload.get("day") or "")
        items = payload.get("items")
        if not DAY_RE.match(day) or not isinstance(items, list):
            return 400, {"error": "send {'day': 'YYYY-MM-DD', 'items': [...]}"}
        if len(items) > MAX_ITEMS:
            return 400, {"error": f"at most {MAX_ITEMS} follow-ups a day"}
        rows, out = [], []
        for n, it in enumerate(items):
            if not isinstance(it, dict):
                return 400, {"error": f"item {n} is not an object"}
            touch = str(it.get("touch") or "")
            phone = us_phone(it.get("phone")) if it.get("phone") else ""
            email = str(it.get("email") or "").strip().lower()
            text = str(it.get("text") or "").strip()
            subject = str(it.get("email_subject") or "").strip()
            body = str(it.get("email_body") or "").strip()
            thread = str(it.get("email_thread_id") or "")
            key = str(it.get("customer_key") or email or phone or "").strip().lower()[:120]
            tz_name = str(it.get("time_zone") or "America/Indiana/Indianapolis")
            due = parse_time(str(it.get("due_at") or "")) if it.get("due_at") else None
            problem = None
            if not TOUCH_RE.match(touch):
                problem = "'touch' must be a short label like '48 hours'"
            elif it.get("phone") and not phone:
                problem = "'phone' must be a US number"
            elif email and not EMAIL_RE.match(email):
                problem = "'email' is not an email address"
            elif not ((phone and text) or (email and body)):
                problem = "needs a phone and text, or an email and email_body"
            elif len(text) > MAX_TEXT or len(body) > MAX_EMAIL or len(subject) > MAX_SUBJECT \
                    or "\n" in subject or "\r" in subject:
                problem = "text, subject or email body is too long"
            elif thread and not THREAD_RE.match(thread):
                problem = "'email_thread_id' looks wrong"
            elif not key or not due:
                problem = "needs 'customer_key' and 'due_at'"
            else:
                try:
                    ZoneInfo(tz_name)
                except Exception:
                    problem = "unknown 'time_zone'"
            if problem:
                return 400, {"error": f"item {n}: {problem}"}
            d = {
                "id": followup_id(key, touch, day), "phone": phone or "", "category": "followup",
                "customer_name": str(it.get("customer_name") or "")[:80] or None, "prospect_id": None,
                "time_zone": tz_name, "body": text if phone else "", "final_body": None, "edited": False,
                "reply_to": None, "customer_said": "", "status": "planned", "reasons": "",
                "created_at": self._stamp(), "send_after": utc_iso(due), "due_at": utc_iso(due),
                "customer_key": key, "touch": touch, "batch_id": day,
                "email_to": email or None, "email_subject": subject or None, "email_body": body or None,
                "email_thread_id": thread or None,
            }
            if phone and self.store.is_dnc(phone):
                d["status"], d["reasons"] = "blocked", "This customer is marked do not contact."
            rows.append(d)
        for d in rows:
            new = self.store.insert_draft_if_new(d)
            out.append({"customer_key": d["customer_key"], "touch": d["touch"], "id": d["id"],
                        "status": d["status"] if new else "already_listed"})
        self._render_batch(day)
        self._log("followups", None, f"{day}: {len(rows)} listed")
        return 200, {"items": out}

    def val_followup_outcomes(self) -> Response:
        rows = self.store.unreported_outcomes(50, category="followup")
        return 200, {"outcomes": [{
            "draft_id": d["id"], "customer_key": d.get("customer_key"), "touch": d.get("touch"),
            "status": d["status"], "sent_at": d.get("sent_at"), "reasons": d.get("reasons") or "",
            "edited": bool(d.get("edited")), "final_text": d.get("final_body") or d.get("body") or "",
            "val_draft": d.get("body") or "", "phone": d.get("phone") or "", "customer_name": d.get("customer_name") or "",
            "email_status": d.get("email_status") or "", "email_error": d.get("email_error") or "",
        } for d in rows]}

    def val_followup_pause(self, payload: dict) -> Response:
        from bridge import us_phone
        phone = us_phone(payload.get("phone")) if payload.get("phone") else ""
        email = str(payload.get("email") or "").strip().lower()
        if not phone and not EMAIL_RE.match(email):
            return 400, {"error": "send a 'phone' or an 'email'"}
        why = str(payload.get("reason") or "The customer wrote back.")[:200]
        n, batches = 0, set()
        for d in self.store.followups_for(OPEN, phone=phone, email=email if EMAIL_RE.match(email) else ""):
            claimed = self.store.claim_draft(d["id"], [d["status"]], {"status": "paused", "reasons": why})
            if claimed:
                n += 1
                batches.add(claimed.get("batch_id"))
                self._edit_card(claimed, self._fu_card_text(claimed, "⏸ Paused: " + why))
        for b in batches:
            self._render_batch(b)
        if n:
            self._log("followups_paused", None, f"{n}: {why}")
        return 200, {"paused": n}

    def val_followup_contacts(self, payload: dict) -> Response:
        """When each phone last texted us, when we last texted them, and do-not-contact.
        Up to 10 phones in 'thread_for' also get their last 8 texts (for Val to write
        a follow-up after a conversation)."""
        from bridge import us_phone
        phones = sorted({p for p in (us_phone(x) for x in (payload.get("phones") or [])[:150]) if p})
        thread_for = {p for p in (us_phone(x) for x in (payload.get("thread_for") or [])[:10]) if p}
        info: Dict[str, dict] = {p: {"last_in": None, "last_out": None, "dnc": False, "thread": []} for p in phones}
        for m in self.store.messages_for_phones(phones):       # newest first
            row = info.get(m["phone"])
            if not row:
                continue
            k = "last_in" if m["direction"] == "in" else "last_out"
            row[k] = row[k] or m["created_at"]
            if m["phone"] in thread_for and len(row["thread"]) < 8:
                row["thread"].insert(0, {"from": "customer" if m["direction"] == "in" else "gerrit",
                                         "text": m["body"][:600], "at": m["created_at"]})
        for p in self.store.dnc_phones(phones):
            info[p]["dnc"] = True
        return 200, {"contacts": info}

    # ------------------------------------------------------------ cards

    def _fu_card_text(self, d: dict, footer: str = "") -> str:
        who = d.get("customer_name") or d.get("email_to") or _pretty(d["phone"])
        due = parse_time(d.get("due_at"))
        lines = [f"🔁 Follow-up to {who} ({d.get('touch')}), {_pretty(d['phone'])}",
                 f"Sends: {_when(due, d['time_zone'])} their time"]
        text = d.get("final_body") or d.get("body")
        if d["phone"] and text:
            lines += ["", "📱 Text:" if not d.get("edited") else "📱 Your edited text:", text]
        if d.get("email_to"):
            subj = "reply in the estimate email" if d.get("email_thread_id") else (d.get("email_subject") or "")
            lines += ["", f"✉️ Email to {d['email_to']} ({subj}):", (d.get("email_body") or "")[:1500]]
        if footer:
            lines += ["", footer]
        return "\n".join(lines)

    @staticmethod
    def _fu_buttons(d: dict) -> list:
        row = [{"text": "✅ Approve", "callback_data": "a:" + d["id"]}]
        if d["phone"]:
            row.append({"text": "✏️ Edit text", "callback_data": "e:" + d["id"]})
        row.append({"text": "✖️ Remove", "callback_data": "s:" + d["id"]})
        return [row, [{"text": "🛑 No more follow-ups for them", "callback_data": "q:" + d["id"]}]]

    def _render_batch(self, batch_id: Optional[str], footer: str = "") -> None:
        if not batch_id:
            return
        drafts = self.store.drafts_in_batch(batch_id)
        if not drafts:
            return
        try:
            label = datetime.strptime(batch_id, "%Y-%m-%d").strftime("%A, %B %-d")
        except ValueError:
            label = batch_id
        lines = [f"🪟 Follow-ups for {label}: {len(drafts)}", ""]
        for n, d in enumerate(drafts, 1):
            who = d.get("customer_name") or d.get("email_to") or _pretty(d["phone"])
            how = ("📱" if d["phone"] and d.get("body") else "") + ("✉️" if d.get("email_to") else "")
            when = _when(parse_time(d.get("due_at")), d["time_zone"])
            row = f"{n}. {ICON.get(d['status'], '•')} {who} · {d.get('touch')} · {when} · {how}"
            if d["status"] in ("paused", "blocked", "expired", "failed") and d.get("reasons"):
                row += f"\n    {d['reasons'][:90]}"
            if d.get("email_status") in ("failed", "refused", "not_set_up"):
                row += f"\n    ✉️ not sent: {(d.get('email_error') or d['email_status'])[:80]}"
            lines.append(row)
        planned = [d for d in drafts if d["status"] == "planned"]
        if planned:
            lines += ["", "Approved ones send at their time (8 AM to 8 PM their time). "
                          "Not approved by 8 PM: nothing sends, and they come back on the next list."]
        if footer:
            lines += ["", footer]
        text = "\n".join(lines)
        if len(text) > 3900:
            text = text[:3850] + "\n…(more in Review one by one)"
        buttons = [[{"text": "✅ Approve all", "callback_data": "fa:" + batch_id}],
                   [{"text": "👀 Review one by one", "callback_data": "fr:" + batch_id}]] if planned else None
        b = self.store.get_batch(batch_id)
        if b and b.get("tg_message_id"):
            self._edit_card({"tg_message_id": b["tg_message_id"]}, text, buttons)
        else:
            msg_id = self._tell_gerrit(text, buttons=buttons)
            if msg_id:
                self.store.save_batch(batch_id, {"tg_message_id": msg_id, "created_at": self._stamp()})

    # ------------------------------------------------------------ taps

    def _fu_tap(self, action: str, key: str, cq: dict) -> bool:
        """Batch buttons (fa, fr) and 'no more follow-ups' (q). True when handled."""
        if action == "fa":
            n = self._fu_approve_all(key)
            self._answer(cq, f"Approved {n}. Each one sends at its time." if n else "Nothing is waiting.")
            return True
        if action == "fr":
            n = 0
            for d in self.store.drafts_in_batch(key):
                claimed = self.store.claim_draft(d["id"], ["planned"], {"status": "pending"}) \
                    if d["status"] == "planned" else None
                if claimed:
                    n += 1
                    msg_id = self._tell_gerrit(self._fu_card_text(claimed), buttons=self._fu_buttons(claimed))
                    if msg_id:
                        self.store.update_draft(d["id"], {"tg_message_id": msg_id})
            self._render_batch(key, "👀 Each one is in its own card below." if n else "")
            self._answer(cq, f"{n} cards below." if n else "Nothing is waiting.")
            return True
        if action == "q":
            _, message = self._fu_stop_customer(key)
            self._answer(cq, message)
            return True
        return False

    def _fu_stop_customer(self, draft_id: str):
        """'No more follow-ups for them': the card's button in Telegram and the same button on the website.
        Every open follow-up for this customer stops; nothing is sent. Returns (how many, Gerrit's answer),
        or (None, answer) when the draft isn't a follow-up."""
        d = self.store.get_draft(draft_id)
        if not d or d["category"] != "followup":
            return None, "I cannot find that follow-up."
        n, batches = 0, set()
        for other in self.store.followups_for(OPEN, phone=d["phone"], email=d.get("email_to") or ""):
            if other.get("customer_key") != d.get("customer_key"):
                continue
            c = self.store.claim_draft(other["id"], [other["status"]], {
                "status": "stopped_customer", "reasons": "Gerrit said: no more follow-ups."})
            if c:
                n += 1
                batches.add(c.get("batch_id"))
                self._edit_card(c, self._fu_card_text(c, "🛑 No more follow-ups for them. Nothing was sent."))
        for b in batches:
            self._render_batch(b)
        self._log("followups_stopped", draft_id, d.get("customer_key") or "")
        return n, ("No more follow-ups for them." if n else "Nothing was waiting for them.")

    def _fu_approve_all(self, batch_id: str, where: str = "") -> int:
        """Approve all: the button on the batch card in Telegram, and the same button on the website's Drafts tab.
        Each planned follow-up is approved; one whose time has come sends now (the send gate still runs)."""
        n = 0
        for d in self.store.drafts_in_batch(batch_id):
            if d["status"] != "planned":
                continue
            claimed = self.store.claim_draft(d["id"], ["planned"], {"status": "held", "approved_at": self._stamp()})
            if claimed:
                n += 1
                due = parse_time(claimed.get("due_at"))
                if due and due <= self.now():
                    now_claim = self.store.claim_draft(d["id"], ["held"], {"status": "approving"})
                    if now_claim:
                        self._send_followup(now_claim)
        self._log("followups_approved", None, f"{batch_id}: {n}" + (f" {where}" if where else ""))
        self._render_batch(batch_id)
        return n

    def _approve_followup(self, d: dict) -> str:
        """d was just claimed ('approving') from its own card."""
        due = parse_time(d.get("due_at"))
        if due and due > self.now():
            self.store.update_draft(d["id"], {"status": "held", "send_after": d["due_at"]})
            d["status"] = "held"
            self._edit_card(d, self._fu_card_text(d, f"⏰ Approved. It sends {_when(due, d['time_zone'])}, their time."))
            self._render_batch(d.get("batch_id"))
            return "Approved. It sends at its time."
        return self._send_followup(d)

    # ------------------------------------------------------------ sending

    def _finish(self, d: dict, fields: dict, footer: str, buttons=None) -> None:
        self.store.update_draft(d["id"], fields)
        d.update(fields)
        self._edit_card(d, self._fu_card_text(d, footer), buttons)
        self._render_batch(d.get("batch_id"))

    def _send_followup(self, d: dict) -> str:
        """d is claimed ('approving'). Checks once more, then sends the text and the email."""
        now = self.now()
        tz = _tz(d["time_zone"])
        local = now.astimezone(tz)
        phone = d["phone"]
        created = parse_time(d.get("created_at"))
        if phone:
            last_in = self.store.latest_inbound(phone)
            if last_in and created and parse_time(last_in["created_at"]) > created:
                self._finish(d, {"status": "paused", "reasons": "They texted since the list was made."},
                             "⏸ Not sent: they texted since the list was made. Val drafts a reply instead.")
                self._log("followup_paused", d["id"], "customer texted")
                return "Paused: they texted."
            if self.store.is_dnc(phone):
                self._finish(d, {"status": "blocked", "reasons": "This customer is marked do not contact."},
                             "⛔ Not sent: do not contact.")
                return "Not sent: do not contact."
        if local.time() < send_gate.SEND_WINDOW_START:
            at = local.replace(hour=8, minute=0, second=0, microsecond=0)
            self._finish(d, {"status": "held", "send_after": utc_iso(at)}, f"⏰ Approved. It sends {_when(at, d['time_zone'])}.")
            return "Approved. It waits until 8 AM their time."
        if local.time() >= send_gate.SEND_WINDOW_END:
            self._finish(d, {"status": "expired", "reasons": "It was after 8 PM their time. It goes on the next list."},
                         "⌛ Not sent: it was after 8 PM their time. It goes on the next list.")
            return "Too late today. It goes on the next list."

        fields: dict = {}
        text = d.get("final_body") or d.get("body") or ""
        text_sent = bool(d.get("quo_message_id"))
        if phone and text and not text_sent:
            try:
                quo_id = self.quo.send_text(phone, text)
            except QuoError as e:
                note = ("⚠️ No answer from Quo. Check the Quo app before you tap Approve again." if e.unknown
                        else f"⚠️ The text did not send: {e} Tap Approve to try again.")
                self._finish(d, {"status": "failed", "error": str(e)}, note, self._fu_buttons(d))
                if not d.get("tg_message_id"):
                    msg_id = self._tell_gerrit(self._fu_card_text(d, note), buttons=self._fu_buttons(d))
                    if msg_id:
                        self.store.update_draft(d["id"], {"tg_message_id": msg_id})
                self._log("send_failed", d["id"], str(e))
                return "Quo did not send the text."
            stamp = self._stamp()
            fields.update(quo_message_id=quo_id, error=None)
            self.store.add_message({"id": quo_id or "out-" + d["id"], "phone": phone, "direction": "out",
                                    "body": text, "created_at": stamp})
            text_sent = True
            self.store.update_draft(d["id"], {"quo_message_id": quo_id})   # never send it twice

        email_sent = bool(d.get("email_sent_at"))
        if d.get("email_to") and not email_sent:
            fields.update(self._send_email(d))
            email_sent = fields.get("email_status") == "sent"

        if text_sent or email_sent:
            fields.update(status="sent", sent_at=self._stamp(), send_after=None)
            note = f"✅ Sent {_when(now, d['time_zone'])}."
            if d.get("email_to") and not email_sent:
                note += f"\n✉️ The email did not send: {fields.get('email_error') or fields.get('email_status')}"
            self._finish(d, fields, note)
            self._log("sent", d["id"], f"followup text={text_sent} email={email_sent}")
            return "Sent."
        # Nothing could go: an email-only follow-up whose email failed.
        status = "blocked" if fields.get("email_status") in ("not_set_up", "refused") else "failed"
        why = fields.get("email_error") or "The email did not send."
        fields.update(status=status, reasons=why)
        self._finish(d, fields, f"⚠️ Not sent: {why}", self._fu_buttons(d) if status == "failed" else None)
        return "Not sent."

    def _send_email(self, d: dict) -> dict:
        if not self.email:
            return {"email_status": "not_set_up", "email_error": "Email sending is not set up yet."}
        to = d["email_to"]
        try:
            if not self.email.got_estimate(to):
                return {"email_status": "refused",
                        "email_error": "This address never got an estimate email from Gerrit."}
            self.email.send(to, d.get("email_subject") or "Following up on your Zinga's estimate",
                            d.get("email_body") or "", d.get("email_thread_id") or "")
        except EmailError as e:
            return {"email_status": "failed", "email_error": str(e)[:200]}
        return {"email_status": "sent", "email_sent_at": self._stamp(), "email_error": None}

    # ------------------------------------------------------------ every minute

    def _fu_tick(self) -> int:
        """Not approved by 8 PM (Gerrit's time) on its day: nothing sends."""
        now = self.now().astimezone(GERRIT_TZ)
        today = now.strftime("%Y-%m-%d")
        late = now.time() >= time(20, 0)
        n, batches = 0, set()
        for d in self.store.drafts_by_status(["planned", "pending", "editing"], 500):
            if d["category"] != "followup" or not d.get("batch_id"):
                continue
            if d["batch_id"] < today or (d["batch_id"] == today and late):
                c = self.store.claim_draft(d["id"], [d["status"]], {
                    "status": "expired", "reasons": "Not approved by 8 PM. It goes on the next list."})
                if c:
                    n += 1
                    batches.add(c["batch_id"])
                    self._edit_card(c, self._fu_card_text(c, "⌛ Not approved by 8 PM. Nothing was sent. "
                                                             "It goes on the next list."))
        for b in batches:
            self._render_batch(b)
        return n
