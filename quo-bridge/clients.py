"""The two outside services quo-bridge talks to: Quo (texts) and Telegram
(the Val Approvals bot). Standard library only.

verify_quo_signature() follows Quo's own steps (docs 2026-03-30, "Webhook
signature validation"): HMAC-SHA256 over "{webhook-id}.{webhook-timestamp}.{raw
body}" with the base64-decoded whsec_ key, compared in constant time, and
rejected when the timestamp is more than 5 minutes off.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import List, Mapping, Optional

QUO_API = "https://api.quo.com"
QUO_API_VERSION = "2026-03-30"
MAX_SKEW_SECONDS = 300


def verify_quo_signature(headers: Mapping[str, str], raw_body: bytes, secret: str,
                         now: Optional[float] = None) -> bool:
    msg_id = headers.get("webhook-id", "")
    ts = headers.get("webhook-timestamp", "")
    sig_header = headers.get("webhook-signature", "")
    if not (secret and msg_id and ts and sig_header):
        return False
    try:
        stamp = int(ts)
    except ValueError:
        return False
    if abs((now if now is not None else time.time()) - stamp) > MAX_SKEW_SECONDS:
        return False
    key_b64 = secret[len("whsec_"):] if secret.startswith("whsec_") else secret
    try:
        key = base64.b64decode(key_b64)
    except (binascii.Error, ValueError):
        return False
    expected = hmac.new(key, f"{msg_id}.{ts}.".encode() + raw_body, hashlib.sha256).digest()
    for entry in sig_header.split(" "):
        if not entry.startswith("v1,"):
            continue
        try:
            got = base64.b64decode(entry[3:])
        except (binascii.Error, ValueError):
            continue
        if hmac.compare_digest(got, expected):
            return True
    return False


def sign_quo_body(raw_body: bytes, secret: str, msg_id: str, ts: int) -> str:
    """The signature header Quo would send. Used by the tests and the setup check."""
    key = base64.b64decode(secret[len("whsec_"):] if secret.startswith("whsec_") else secret)
    sig = hmac.new(key, f"{msg_id}.{ts}.".encode() + raw_body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(sig).decode()


class QuoError(RuntimeError):
    def __init__(self, message: str, status: int = 0, unknown: bool = False):
        super().__init__(message)
        self.status = status
        self.unknown = unknown   # True when we can't tell if the text went out


def quo_said(raw) -> str:
    """Quo's own words from an error body, short, for the card and the log."""
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        text = (raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw or "")).strip()
        return text[:240] if text and "<" not in text else ""
    if not isinstance(body, dict):
        return ""
    if isinstance(body.get("error"), dict):
        body = dict(body, **body["error"])
    parts = [str(body.get(k)).strip() for k in ("title", "message") if body.get(k)]
    for err in (body.get("errors") or [])[:2]:
        if isinstance(err, dict) and err.get("message"):
            parts.append(str(err["message"]).strip())
    seen = []
    for x in parts:
        if x and x not in seen:
            seen.append(x)
    return " ".join(seen)[:240]


def quo_error(status: int, raw=b"") -> "QuoError":
    reason = _QUO_REASONS.get(status, f"Quo error {status}.")
    said = quo_said(raw)
    return QuoError(f"{reason} Quo said: {said}" if said else reason, status=status)


# Quo's firewall (Cloudflare) refuses Python's default "Python-urllib" name tag
# with "error code: 1010", so every Quo call names itself.
USER_AGENT = "zingas-quo-bridge/1.0"

_QUO_REASONS = {
    400: "Quo refused it (texting registration not approved, or a bad number).",
    401: "Quo didn't accept the key.",
    402: "The Quo subscription has expired.",
    403: "Quo's daily texting limit was reached, or this number can't send.",
    429: "Quo says too many texts right now. Try again in a minute.",
}


class QuoClient:
    def __init__(self, api_key: str, from_number_id: str, timeout: float = 15.0):
        self.api_key = api_key
        self.from_number_id = from_number_id
        self.timeout = timeout

    def _call(self, method: str, path: str, body=None, versioned: bool = True) -> dict:
        headers = {"Authorization": self.api_key, "Content-Type": "application/json",
                   "Accept": "application/json", "User-Agent": USER_AGENT}
        if versioned:
            headers["Quo-Api-Version"] = QUO_API_VERSION
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(QUO_API + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            try:
                body = e.read()
            except Exception:
                body = b""
            raise quo_error(e.code, body) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise QuoError(f"No answer from Quo ({type(e).__name__}).", unknown=True) from None
        return json.loads(raw) if raw else {}

    def send_text(self, to: str, text: str) -> str:
        """Send one text from the business number. Returns Quo's message id.
        Sending is only in Quo's v1 API ("Send a text message")."""
        out = self._call("POST", "/v1/messages",
                         {"content": text, "from": self.from_number_id, "to": [to]}, versioned=False)
        return str((out.get("data") or {}).get("id", ""))

    def list_numbers(self) -> List[dict]:
        return list(self._call("GET", "/phone-numbers?limit=50").get("data") or [])

    def list_webhooks(self) -> List[dict]:
        return list(self._call("GET", "/webhooks").get("data") or [])

    def delete_webhook(self, webhook_id: str) -> None:
        self._call("DELETE", "/v1/webhooks/" + webhook_id, versioned=False)

    def create_webhook(self, url: str, number_id: str, events=("message.received",),
                       label: str = "zingas-bridge") -> dict:
        return self._call("POST", "/webhooks", {
            "url": url, "events": list(events), "resourceIds": [number_id],
            "label": label}).get("data") or {}


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, timeout: float = 10.0):
        self.token = token
        self.timeout = timeout

    def call(self, method: str, payload: dict) -> dict:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/{method}",
            data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            # Never echo the URL: it holds the bot token.
            raise TelegramError(f"Telegram {method}: HTTP {e.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise TelegramError(f"Telegram {method}: {type(e).__name__}") from None
        if not out.get("ok"):
            raise TelegramError(f"Telegram {method}: {out.get('description', 'failed')}")
        return out.get("result") or {}

    def send(self, chat_id: int, text: str, buttons: Optional[list] = None,
             force_reply: bool = False) -> int:
        payload = {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        elif force_reply:
            payload["reply_markup"] = {"force_reply": True}
        return int(self.call("sendMessage", payload).get("message_id", 0))

    def edit(self, chat_id: int, message_id: int, text: str, buttons: Optional[list] = None) -> None:
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text[:4000],
                   "disable_web_page_preview": True,
                   "reply_markup": {"inline_keyboard": buttons or []}}
        self.call("editMessageText", payload)

    def answer(self, callback_id: str, text: str = "") -> None:
        self.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:180]})


# ---------------------------------------------------------------- Gmail (F0)

COMPOSIO_API = "https://backend.composio.dev/api/v3.1"


class EmailError(RuntimeError):
    pass


class ComposioGmail:
    """Sends Gerrit's approved follow-up emails from his zingashome Gmail, through
    Composio with the MAIN key (Zingas Bridge vault). Only quo-bridge holds it.
    It does two things only: check that an address got an estimate from Gerrit,
    and send one email (as a reply in the estimate's thread when we know it)."""

    def __init__(self, api_key: str, account_id: str, user_id: str = "gerrit",
                 timeout: float = 30.0, api: str = COMPOSIO_API):
        self.api_key, self.account_id, self.user_id = api_key, account_id, user_id
        self.timeout, self.api = timeout, api

    def _execute(self, tool: str, arguments: dict) -> dict:
        body = {"connected_account_id": self.account_id, "user_id": self.user_id, "arguments": arguments}
        req = urllib.request.Request(f"{self.api}/tools/execute/{tool}", data=json.dumps(body).encode(),
                                     method="POST", headers={"x-api-key": self.api_key, "User-Agent": USER_AGENT,
                                                             "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise EmailError(f"Composio {tool}: HTTP {e.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise EmailError(f"Composio {tool}: {type(e).__name__}") from None
        if out.get("successful") is False or out.get("error"):
            msg = out.get("error")
            msg = msg.get("message") if isinstance(msg, dict) else msg
            raise EmailError(f"Composio {tool}: {str(msg or 'failed')[:200]}")
        return out.get("data") or {}

    def got_estimate(self, email: str) -> bool:
        """True when Gerrit's Sent mail has an estimate email to this address."""
        data = self._execute("GMAIL_FETCH_EMAILS", {"query": f"in:sent to:{email} subject:estimate",
                                                    "max_results": 1, "verbose": False,
                                                    "include_payload": False, "include_spam_trash": False})
        return bool(data.get("messages"))

    def send(self, to: str, subject: str, body: str, thread_id: str = "") -> str:
        if thread_id:
            data = self._execute("GMAIL_REPLY_TO_THREAD", {"thread_id": thread_id, "recipient_email": to,
                                                           "message_body": body, "is_html": False})
        else:
            data = self._execute("GMAIL_SEND_EMAIL", {"recipient_email": to, "subject": subject,
                                                      "body": body, "is_html": False})
        inner = data.get("response_data") if isinstance(data.get("response_data"), dict) else data
        return str(inner.get("id") or inner.get("messageId") or "")
