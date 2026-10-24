"""quo-bridge: the only way a text reaches a customer.

Four ways in, each with its own lock:
  - Quo's text and call alerts (signed by Quo)    -> handle_quo()
  - Val's computer, with the drafts-only code       -> val_updates(), val_ack(), val_draft()
  - Gerrit's taps in the Val Approvals bot          -> handle_telegram()
  - Vercel's every-minute timer (CRON_SECRET)       -> tick()

Val's code can only hand over drafts and pick up new texts. Every send goes
through send_gate.decide() first, and only an Approve tap from Gerrit's own
Telegram account (or, much later, a kind of text that has earned auto-send
AND the AUTO_SEND_ENABLED switch) can make it send.
"""

from __future__ import annotations

import hmac
import json
import re
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo

import send_gate
from clients import QuoError, TelegramError, verify_quo_signature
from followups import FollowupMixin
from store import parse_time, utc_iso

DEFAULT_TIME_ZONE = "America/Indiana/Indianapolis"
MAX_PENDING = 30           # if Val's code leaked, the worst case is this many cards
MAX_TEXT = 1600            # Quo's limit for one text
STOP_WORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "OPTOUT", "REVOKE"}
START_WORDS = {"START", "UNSTOP"}
_CATEGORY_RE = re.compile(r"^[a-z_]{1,32}$")
CALL_EVENTS = ("call.completed", "call.voicemail.completed", "call.summary.completed")

Response = Tuple[int, dict]


@dataclass
class Config:
    quo_webhook_secret: str
    telegram_webhook_secret: str
    approver_id: int
    val_token: str
    cron_secret: str
    gerrit_cell: str = ""
    auto_send_enabled: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Config":
        return cls(
            quo_webhook_secret=env.get("QUO_WEBHOOK_SECRET", ""),
            telegram_webhook_secret=env.get("APPROVALS_WEBHOOK_SECRET", ""),
            approver_id=int(env.get("APPROVER_TELEGRAM_ID", "0") or 0),
            val_token=env.get("VAL_DRAFT_TOKEN", ""),
            cron_secret=env.get("CRON_SECRET", ""),
            gerrit_cell=env.get("GERRIT_CELL", ""),
            auto_send_enabled=env.get("AUTO_SEND_ENABLED", "").lower() == "true",
        )


def bearer_ok(headers: Mapping[str, str], secret: str) -> bool:
    """Constant-time check of 'Authorization: Bearer <secret>'. An empty secret never matches."""
    if not secret:
        return False
    got = headers.get("authorization", "")
    return hmac.compare_digest(got.encode(), ("Bearer " + secret).encode())


def us_phone(value) -> Optional[str]:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return "+1" + digits if len(digits) == 10 else None


def pretty_phone(e164: str) -> str:
    d = e164[-10:]
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else e164


def _local(dt: datetime, tz_name: str) -> str:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo(DEFAULT_TIME_ZONE)
    return dt.astimezone(tz).strftime("%a %-I:%M %p")


class Bridge(FollowupMixin):
    def __init__(self, config: Config, store, quo, telegram,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc), email=None):
        self.cfg = config
        self.email = email          # ComposioGmail for F0 follow-up emails, or None
        self.store = store
        self.quo = quo
        self.tg = telegram
        self.now = now

    # ------------------------------------------------------------------ helpers

    def _stamp(self) -> str:
        return utc_iso(self.now())

    def _log(self, kind: str, draft_id: Optional[str], detail: str) -> None:
        try:
            self.store.log(kind, draft_id, detail, self._stamp())
        except Exception as e:  # the log must never stop a send or a reply
            print(f"log failed: {type(e).__name__}", file=sys.stderr)

    def _tell_gerrit(self, text: str, buttons=None, force_reply: bool = False) -> int:
        try:
            return self.tg.send(self.cfg.approver_id, text, buttons=buttons, force_reply=force_reply)
        except TelegramError as e:
            print(f"telegram send failed: {e}", file=sys.stderr)
            return 0

    def _edit_card(self, d: dict, text: str, buttons=None) -> None:
        if not d.get("tg_message_id"):
            return
        try:
            self.tg.edit(self.cfg.approver_id, int(d["tg_message_id"]), text, buttons)
        except TelegramError as e:
            print(f"telegram edit failed: {e}", file=sys.stderr)

    @staticmethod
    def _text_of(d: dict) -> str:
        return d.get("final_body") or d["body"]

    def _card_text(self, d: dict, footer: str = "") -> str:
        if d.get("category") == "followup":
            return self._fu_card_text(d, footer)
        who = d.get("customer_name") or "a customer"
        lines = [f"📱 Text to {who}, {pretty_phone(d['phone'])}", f"Kind: {d['category']}"]
        if d.get("customer_said"):
            lines += ["", "They wrote:", d["customer_said"][:1200]]
        lines += ["", "Val's draft:" if not d.get("edited") else "Your edited text:", self._text_of(d)]
        flags = send_gate.needs_gerrit(d.get("customer_said") or "")
        if flags:
            lines += ["", "⚠️ " + " ".join(flags)]
        if footer:
            lines += ["", footer]
        return "\n".join(lines)

    @staticmethod
    def _buttons(d: dict) -> list:
        if d.get("category") == "followup":
            return FollowupMixin._fu_buttons(d)
        return [[{"text": "✅ Approve", "callback_data": "a:" + d["id"]},
                 {"text": "✏️ Edit", "callback_data": "e:" + d["id"]},
                 {"text": "✖️ Skip", "callback_data": "s:" + d["id"]}]]

    def _stats(self, category: str) -> send_gate.AutoSendStats:
        row = self.store.get_stats(category)
        return send_gate.AutoSendStats(category, int(row.get("streak") or 0), bool(row.get("enabled")))

    def _save_stats(self, s: send_gate.AutoSendStats) -> None:
        self.store.save_stats(s.category, s.approvals_in_a_row_unedited, s.enabled)

    @staticmethod
    def _held_buttons(d: dict) -> list:
        return [[{"text": "📤 Send now", "callback_data": "n:" + d["id"]},
                 {"text": "✖️ Cancel", "callback_data": "s:" + d["id"]}]]

    def _outgoing(self, d: dict, approved: bool, send_now: bool = False) -> send_gate.OutgoingText:
        return send_gate.OutgoingText(
            text=self._text_of(d), category=d["category"], customer_time_zone=d["time_zone"],
            prospect_id=d.get("prospect_id") or None, do_not_contact=self.store.is_dnc(d["phone"]),
            approved_by_gerrit=approved, in_reply_to=d.get("customer_said") or "",
            gerrit_said_send_now=send_now)

    # ------------------------------------------------------------- 1. Quo alert

    def handle_quo(self, headers: Mapping[str, str], raw: bytes) -> Response:
        # One secret per Quo alert subscription (texts and calls may be two), comma-separated.
        secrets_ = [x.strip() for x in self.cfg.quo_webhook_secret.split(",") if x.strip()]
        if not any(verify_quo_signature(headers, raw, sec, now=self.now().timestamp()) for sec in secrets_):
            return 401, {"error": "bad signature"}
        try:
            event = json.loads(raw)
        except ValueError:
            return 200, {"ignored": "not json"}
        if event.get("type") in CALL_EVENTS:
            return self._on_call(event)
        if event.get("type") != "message.received":
            return 200, {"ignored": event.get("type")}
        data = event.get("data") or {}
        res, ctx = data.get("resource") or {}, data.get("context") or {}
        phone = us_phone(ctx.get("senderIdentifier"))
        if not res.get("id") or res.get("direction") != "incoming" or not phone:
            return 200, {"ignored": "not an incoming text from a US number"}
        text = str(res.get("text") or "").strip()
        if not text and res.get("media"):
            text = "[picture or file]"
        new = self.store.add_message({"id": str(res["id"]), "phone": phone, "direction": "in",
                                      "body": text[:MAX_TEXT], "created_at": res.get("createdAt") or self._stamp()})
        if not new:
            return 200, {"duplicate": True}
        word = re.sub(r"[^A-Z]", "", text.upper())
        if word in STOP_WORDS:
            self.store.set_dnc(phone, True, self._stamp())
            for d in self.store.drafts_by_status(["pending", "editing", "held", "countdown", "failed"]):
                if d["phone"] == phone and self.store.claim_draft(
                        d["id"], [d["status"]], {"status": "blocked", "reasons": "Customer texted STOP."}):
                    self._edit_card(d, self._card_text(d, "⛔ Not sent: they texted STOP."))
            self._log("dnc_on", None, phone)
            self._tell_gerrit(f"🚫 {pretty_phone(phone)} texted \"{text[:40]}\". This number is now do-not-contact. "
                              "Val will not send texts to this number again.")
        elif word in START_WORDS:
            self.store.set_dnc(phone, False, self._stamp())
            self._log("dnc_off", None, phone)
            self._tell_gerrit(f"✅ {pretty_phone(phone)} texted START. They can get texts again.")
        return 200, {"stored": True}

    def _on_call(self, event: dict) -> Response:
        """Calls and voicemails go on Val's to-do list. Only incoming calls from a US
        number are kept: a missed call with no voicemail, a voicemail (with Quo's
        transcript), or an answered call's summary (Quo's Business plan)."""
        kind_of = event.get("type")
        data = event.get("data") or {}
        res, ctx = data.get("resource") or {}, data.get("context") or {}
        external = (ctx.get("participants") or {}).get("external") or []
        if kind_of == "call.completed":
            if res.get("direction") != "incoming" or res.get("hasVoicemail"):
                return 200, {"ignored": "not a missed call"}     # the voicemail alert covers it
            if res.get("status") not in ("unanswered", "abandoned", "failed"):
                return 200, {"ignored": "answered call"}          # the summary alert covers it
            phone, kind, body, row_id = us_phone(external[0] if external else ""), "missed", "", res.get("id")
        elif kind_of == "call.voicemail.completed":
            if res.get("direction") not in (None, "incoming"):
                return 200, {"ignored": "outgoing"}
            phone = us_phone(res.get("from") or (external[0] if external else ""))
            kind, row_id = "voicemail", res.get("id") or res.get("voicemailId")
            body = str(res.get("transcript") or "").strip() or "[Quo had no transcript yet. Listen in the Quo app.]"
        else:   # call.summary.completed
            if res.get("processingStatus") != "completed":
                return 200, {"ignored": "summary not ready"}
            phone = us_phone(res.get("fromPhoneNumber") or (external[0] if external else ""))
            kind, row_id = "call_summary", "sum-" + str(res.get("callId") or "")
            lines = [str(x) for x in (res.get("summary") or [])]
            steps = [str(x) for x in (res.get("nextSteps") or [])]
            body = "\n".join(lines + (["Next steps:"] + steps if steps else []))
        if not row_id or row_id == "sum-" or not phone:
            return 200, {"ignored": "no id or not a US number"}
        new = self.store.add_call({"id": str(row_id), "phone": phone, "kind": kind, "body": body[:4000],
                                   "created_at": res.get("createdAt") or res.get("completedAt") or self._stamp()})
        return 200, ({"stored": True} if new else {"duplicate": True})

    # ------------------------------------------------------- 2. Val's computer

    def val_updates(self) -> Response:
        texts = []
        for m in self.store.unpicked_messages(20):
            thread = [{"from": "customer" if t["direction"] == "in" else "gerrit",
                       "text": t["body"], "at": t["created_at"]}
                      for t in self.store.recent_messages(m["phone"], 10)]
            texts.append({"id": m["id"], "phone": m["phone"], "text": m["body"], "received_at": m["created_at"],
                          "do_not_contact": self.store.is_dnc(m["phone"]), "thread": thread})
        outcomes = [{"draft_id": d["id"], "phone": d["phone"], "category": d["category"],
                     "status": d["status"], "val_draft": d["body"], "final_text": self._text_of(d),
                     "edited": bool(d.get("edited")), "sent_at": d.get("sent_at"),
                     "reasons": d.get("reasons") or ""}
                    for d in self.store.unreported_outcomes(20, exclude_category="followup")]
        calls = [{"id": c["id"], "phone": c["phone"], "kind": c["kind"], "text": c.get("body") or "",
                  "received_at": c["created_at"]} for c in self.store.unpicked_calls(20)]
        return 200, {"texts": texts, "outcomes": outcomes, "calls": calls}

    def val_ack(self, payload: dict) -> Response:
        texts = [str(i) for i in (payload.get("texts") or [])][:100]
        outcomes = [str(i) for i in (payload.get("outcomes") or [])][:100]
        calls = [str(i) for i in (payload.get("calls") or [])][:100]
        self.store.ack_calls(calls, self._stamp())
        self.store.ack_messages(texts, self._stamp())
        self.store.mark_reported(outcomes, self._stamp())
        return 200, {"ok": True}

    def val_draft(self, payload: dict) -> Response:
        phone = us_phone(payload.get("to"))
        if not phone:
            return 400, {"error": "'to' must be a US phone number"}
        body = str(payload.get("text") or "").strip()
        if not body or len(body) > MAX_TEXT:
            return 400, {"error": f"'text' must be 1 to {MAX_TEXT} characters"}
        category = str(payload.get("category") or "reply")
        if not _CATEGORY_RE.match(category):
            return 400, {"error": "'category' must be lowercase letters and _"}
        tz_name = str(payload.get("time_zone") or DEFAULT_TIME_ZONE)
        try:
            ZoneInfo(tz_name)
        except Exception:
            return 400, {"error": "unknown 'time_zone'"}
        if self.store.is_dnc(phone):
            return 409, {"error": "This customer is do-not-contact. No card was made."}
        waiting = [x for x in self.store.drafts_by_status(["pending", "editing", "countdown"], 200)
                   if x["category"] != "followup"]
        if len(waiting) >= MAX_PENDING:
            return 429, {"error": f"{MAX_PENDING} drafts are already waiting for Gerrit."}

        # What the customer said comes from our own records, never from Val, so
        # the money / upset / "real person" checks can't be talked around.
        said_msg = None
        if payload.get("reply_to"):
            said_msg = self.store.get_message(str(payload["reply_to"]))
            if said_msg and said_msg["phone"] != phone:
                said_msg = None
        if not said_msg:
            said_msg = self.store.latest_inbound(phone)

        d = {
            "id": secrets.token_hex(5),
            "phone": phone,
            "customer_name": str(payload.get("customer_name") or "")[:80] or None,
            "prospect_id": str(payload.get("prospect_id") or "")[:40] or None,
            "time_zone": tz_name,
            "category": category,
            "body": body,
            "final_body": None,
            "edited": False,
            "reply_to": said_msg["id"] if said_msg else None,
            "customer_said": said_msg["body"] if said_msg else "",
            "status": "pending",
            "reasons": "",
            "created_at": self._stamp(),
        }
        decision = send_gate.decide(self._outgoing(d, approved=False), self.now(), self._stats(category))
        d["reasons"] = " ".join(decision.reasons)
        if decision.action == "block":
            d["status"] = "blocked"
            self.store.insert_draft(d)
            self._log("blocked", d["id"], d["reasons"])
            return 200, {"id": d["id"], "status": "blocked", "reasons": decision.reasons}
        if decision.action == "countdown" and self.cfg.auto_send_enabled:
            d["status"] = "countdown"
            d["send_after"] = utc_iso(decision.send_after)
            self.store.insert_draft(d)
            when = _local(decision.send_after, tz_name)
            msg_id = self._tell_gerrit(self._card_text(d, f"⏳ Sends by itself at {when} unless you tap Stop."),
                                       buttons=[[{"text": "🛑 Stop", "callback_data": "x:" + d["id"]}]])
        else:
            self.store.insert_draft(d)
            msg_id = self._tell_gerrit(self._card_text(d), buttons=self._buttons(d))
        if msg_id:
            self.store.update_draft(d["id"], {"tg_message_id": msg_id})
        self._log("draft", d["id"], d["status"])
        return 200, {"id": d["id"], "status": d["status"]}

    # ----------------------------------------------------------- sending

    def _send_now(self, d: dict, approved: bool, send_now: bool = False) -> str:
        """d is already claimed (status 'approving' or 'sending'). Runs the gate
        once more, then sends, holds or blocks. Returns a short result line.
        send_now=True means Gerrit tapped Send now on a held text."""
        if d.get("category") == "followup":
            return self._send_followup(d)
        decision = send_gate.decide(self._outgoing(d, approved, send_now), self.now(),
                                    None if approved else self._stats(d["category"]))
        ok_to_send = decision.action == "send" or (not approved and decision.action == "countdown")
        if decision.action == "hold":
            when = _local(decision.send_after, d["time_zone"])
            self.store.update_draft(d["id"], {"status": "held", "send_after": utc_iso(decision.send_after)})
            self._edit_card(d, self._card_text(d, f"⏰ Approved. It sends {when}, their time. "
                                                  f"To send it now, tap 📤 Send now."),
                            self._held_buttons(d))
            self._log("held", d["id"], " ".join(decision.reasons))
            return "Approved. The text waits until 8 AM in their time zone."
        if not ok_to_send:
            reasons = " ".join(decision.reasons)
            if decision.action == "block":
                self.store.update_draft(d["id"], {"status": "blocked", "reasons": reasons})
                self._edit_card(d, self._card_text(d, "⛔ Not sent: " + reasons))
                self._log("blocked", d["id"], reasons)
                return "Not sent."
            # An auto-send that no longer passes: back to Gerrit.
            self.store.update_draft(d["id"], {"status": "pending", "reasons": reasons, "send_after": None})
            self._edit_card(d, self._card_text(d, "👀 This draft needs your approval: " + reasons), self._buttons(d))
            self._log("needs_approval", d["id"], reasons)
            return "Needs Gerrit."
        try:
            quo_id = self.quo.send_text(d["phone"], self._text_of(d))
        except QuoError as e:
            if e.unknown:
                status, buttons = "failed", self._buttons(d)
                note = "⚠️ No answer from Quo. Check the Quo app before you tap Approve again."
            elif send_now:   # keep it approved and waiting; Send now tries again
                status, buttons = "held", self._held_buttons(d)
                note = f"⚠️ The text did not send: {e} It still sends at 8 AM. To try again now, tap 📤 Send now."
            else:
                status, buttons = "pending", self._buttons(d)
                note = f"⚠️ The text did not send: {e} Tap Approve to try again."
            self.store.update_draft(d["id"], {"status": status, "error": str(e)})
            self._edit_card(d, self._card_text(d, note), buttons)
            self._log("send_failed", d["id"], str(e))
            return "Quo did not send the text."
        stamp = self._stamp()
        self.store.update_draft(d["id"], {"status": "sent", "sent_at": stamp, "quo_message_id": quo_id,
                                          "error": None, "send_after": None})
        self.store.add_message({"id": quo_id or "out-" + d["id"], "phone": d["phone"], "direction": "out",
                                "body": self._text_of(d), "created_at": stamp})
        self._edit_card(d, self._card_text(d, f"✅ Sent {_local(self.now(), DEFAULT_TIME_ZONE)}."))
        self._log("sent", d["id"], quo_id)
        return "Sent."

    # ------------------------------------------------------- 3. Gerrit's taps

    def handle_telegram(self, headers: Mapping[str, str], raw: bytes) -> Response:
        expected = self.cfg.telegram_webhook_secret
        got = headers.get("x-telegram-bot-api-secret-token", "")
        if not expected or not hmac.compare_digest(got.encode(), expected.encode()):
            return 401, {"error": "bad secret"}
        try:
            update = json.loads(raw)
        except ValueError:
            return 200, {}
        if update.get("callback_query"):
            self._on_tap(update["callback_query"])
        elif update.get("message"):
            self._on_message(update["message"])
        return 200, {}

    def _answer(self, cq: dict, text: str) -> None:
        try:
            self.tg.answer(cq.get("id", ""), text)
        except TelegramError as e:
            print(f"telegram answer failed: {e}", file=sys.stderr)

    def _on_tap(self, cq: dict) -> None:
        if int((cq.get("from") or {}).get("id") or 0) != self.cfg.approver_id:
            self._answer(cq, "Only Gerrit can do this.")
            return
        action, _, draft_id = str(cq.get("data") or "").partition(":")
        if action in ("fa", "fr", "q") and self._fu_tap(action, draft_id, cq):
            return
        d = self.store.get_draft(draft_id)
        if not d:
            self._answer(cq, "I cannot find that draft.")
            return
        if action == "a":
            claimed = self.store.claim_draft(draft_id, ["pending", "failed"],
                                             {"status": "approving", "approved_at": d.get("approved_at") or self._stamp()})
            if not claimed:
                self._answer(cq, "Someone already did an action on this draft.")
                return
            if d["category"] == "followup":
                self._answer(cq, self._approve_followup(claimed))
                return
            if not d.get("approved_at"):   # count each draft once toward auto-send
                stats = self._stats(d["category"])
                stats.record_approval(edited=bool(d.get("edited")))
                self._save_stats(stats)
            self._answer(cq, self._send_now(claimed, approved=True))
        elif action == "n":
            claimed = self.store.claim_draft(draft_id, ["held"], {"status": "approving"})
            if not claimed:
                self._answer(cq, "Someone already did an action on this draft.")
                return
            self._log("send_now", draft_id, "Gerrit tapped Send now outside 8am to 8pm.")
            self._answer(cq, self._send_now(claimed, approved=True, send_now=True))
        elif action == "s":
            claimed = self.store.claim_draft(draft_id, ["pending", "editing", "held", "failed"], {"status": "skipped"})
            if claimed:
                self._edit_card(claimed, self._card_text(claimed, "✖️ Skipped. Nothing was sent."))
                self._log("skipped", draft_id, "")
                if claimed["category"] == "followup":
                    self._render_batch(claimed.get("batch_id"))
            self._answer(cq, "Skipped." if claimed else "Someone already did an action on this draft.")
        elif action == "x":
            claimed = self.store.claim_draft(draft_id, ["countdown"], {"status": "stopped"})
            if claimed:
                stats = self._stats(d["category"])
                stats.record_complaint()
                self._save_stats(stats)
                self._edit_card(claimed, self._card_text(claimed, "🛑 Stopped. Nothing was sent. "
                                                                   "This kind of text needs your OK again."))
                self._log("stopped", draft_id, "")
            self._answer(cq, "Stopped." if claimed else "You are too late. The text went out, or someone already did an action on it.")
        elif action == "e":
            if d["category"] == "followup" and not d["phone"]:
                self._answer(cq, "This one is email only. To change it, tap Remove and write it yourself.")
                return
            claimed = self.store.claim_draft(draft_id, ["pending", "failed"], {"status": "editing"})
            if not claimed:
                self._answer(cq, "Someone already did an action on this draft.")
                return
            prompt = self._tell_gerrit(f"✏️ Reply to this message with the new text for "
                                       f"{d.get('customer_name') or pretty_phone(d['phone'])}. [{draft_id}]",
                                       force_reply=True)
            self.store.update_draft(draft_id, {"tg_prompt_id": prompt or None})
            self._answer(cq, "Type the new text.")
        else:
            self._answer(cq, "?")

    def _on_message(self, msg: dict) -> None:
        if int((msg.get("from") or {}).get("id") or 0) != self.cfg.approver_id:
            return
        text = str(msg.get("text") or "").strip()
        if text.startswith("/start"):
            self._tell_gerrit("Val Approvals is ready. Customer text drafts come here with Approve, Edit and Skip buttons.")
            return
        if text.startswith("/waiting"):
            n = len(self.store.drafts_by_status(["pending", "editing"], MAX_PENDING + 1))
            self._tell_gerrit(f"{n} draft(s) need your approval.")
            return
        replied = (msg.get("reply_to_message") or {}).get("message_id")
        d = self.store.find_draft_by_prompt(int(replied)) if replied else None
        if not d:
            editing = self.store.drafts_by_status(["editing"], 2)
            d = editing[0] if len(editing) == 1 else None
        if not d or d["status"] != "editing":
            self._not_an_edit()
            return
        if not text or len(text) > MAX_TEXT:
            self._tell_gerrit(f"The text must be 1 to {MAX_TEXT} characters. Try again.", force_reply=True)
            return
        claimed = self.store.claim_draft(d["id"], ["editing"],
                                         {"status": "pending", "final_body": text, "edited": True, "error": None})
        if not claimed:
            return
        self._edit_card(d, self._card_text(d, "✏️ Edited. See the new card below."))
        msg_id = self._tell_gerrit(self._card_text(claimed), buttons=self._buttons(claimed))
        if msg_id:
            self.store.update_draft(d["id"], {"tg_message_id": msg_id})
        self._log("edited", d["id"], "")

    def _not_an_edit(self) -> None:
        """Gerrit typed a message that is not new text for a draft. The bot
        cannot read typed messages, so it shows him the buttons to use."""
        held = [d for d in self.store.drafts_by_status(["held"], 50) if d["category"] != "followup"][:2]
        if len(held) == 1:
            d = held[0]
            when = _local(parse_time(d.get("send_after")), d["time_zone"]) if d.get("send_after") else "at 8:00 AM"
            who = d.get("customer_name") or pretty_phone(d["phone"])
            self._tell_gerrit(f"I cannot read typed messages. Use the buttons.\n"
                              f"The text to {who} waits until {when}, their time. "
                              f"To send it now, tap 📤 Send now.", buttons=self._held_buttons(d))
            return
        if held:
            self._tell_gerrit("I cannot read typed messages. Use the buttons.\n"
                              "To send a waiting text now, tap 📤 Send now on its card.")
            return
        self._tell_gerrit("I cannot read typed messages. Use the buttons on each draft.\n"
                          "To change a draft, tap ✏️ Edit. Then reply to my message.")

    # ------------------------------------------------- 4. every-minute check

    def tick(self) -> Response:
        now = self.now()
        done = {"sent_or_held": 0, "auto": 0, "escalated": 0, "missed": 0, "followups_expired": 0}

        for d in self.store.drafts_by_status(["held"]):
            due = parse_time(d.get("send_after"))
            if due and due <= now:
                claimed = self.store.claim_draft(d["id"], ["held"], {"status": "approving"})
                if claimed:
                    self._send_now(claimed, approved=True)
                    done["sent_or_held"] += 1

        for d in self.store.drafts_by_status(["countdown"]):
            due = parse_time(d.get("send_after"))
            if not self.cfg.auto_send_enabled:
                claimed = self.store.claim_draft(d["id"], ["countdown"], {"status": "pending", "send_after": None})
                if claimed:
                    self._edit_card(claimed, self._card_text(claimed, "👀 Auto-send is off. This needs your OK."),
                                    self._buttons(claimed))
            elif due and due <= now:
                claimed = self.store.claim_draft(d["id"], ["countdown"], {"status": "sending"})
                if claimed:
                    self._send_now(claimed, approved=False)
                    done["auto"] += 1

        waiting = []
        for d in self.store.drafts_by_status(["pending", "editing"]):
            if d["category"] == "followup":      # follow-up cards are not customer replies
                continue
            created = parse_time(d["created_at"])
            state = send_gate.waiting_status(created, now, handled=False)
            if state == "missed" and not d.get("missed_at"):
                if self.store.claim_draft(d["id"], ["pending", "editing"], {"missed_at": utc_iso(now)},
                                          require_null="missed_at"):
                    done["missed"] += 1
            if state in ("escalate", "missed") and not d.get("escalated_at"):
                waiting.append(d)
        if waiting and self.cfg.gerrit_cell:
            claimed = [d for d in waiting
                       if self.store.claim_draft(d["id"], ["pending", "editing"], {"escalated_at": utc_iso(now)},
                                                 require_null="escalated_at")]
            if claimed:
                n = len(claimed)
                note = ("Val: 1 customer text needs your approval in Val Approvals."
                        if n == 1 else f"Val: {n} customer texts need your approval in Val Approvals.")
                try:
                    self.quo.send_text(self.cfg.gerrit_cell, note)
                    done["escalated"] = n
                    self._log("escalated", None, str(n))
                except QuoError as e:
                    for d in claimed:
                        self.store.update_draft(d["id"], {"escalated_at": None})
                    self._log("escalate_failed", None, str(e))
        done["followups_expired"] = self._fu_tick()
        return 200, done
