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
                   "Accept": "application/json"}
        if versioned:
            headers["Quo-Api-Version"] = QUO_API_VERSION
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(QUO_API + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise QuoError(_QUO_REASONS.get(e.code, f"Quo error {e.code}."), status=e.code) from None
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
