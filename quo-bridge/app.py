"""Vercel entry point for quo-bridge: a plain WSGI app, standard library only.

  POST /api/quo          Quo's "new text" alert (Quo's signature)
  GET  /api/val/updates  new customer texts + draft outcomes (Val's code)
  POST /api/val/ack      Val's computer says what it picked up (Val's code)
  POST /api/val/drafts   Val hands over a draft (Val's code)
  POST /api/telegram     Gerrit's taps in Val Approvals (Telegram's secret header)
  GET  /api/tick         every-minute check (Vercel's CRON_SECRET)
  GET  /api/health       {"ok": true}, no secrets needed
  F0 quote follow-ups (Val's code):
  POST /api/val/followups           the day's follow-up list -> one card in Val Approvals
  GET  /api/val/followups/outcomes  what happened to each follow-up
  POST /api/val/followups/pause     a customer wrote back: hold their follow-ups
  POST /api/val/followups/contacts  last text in/out and do-not-contact, for a list of phones
  Zinga's OS (the company website), only with ZINGAS_OS_TOKEN:
  GET  /api/os/drafts    drafts waiting on Gerrit, read-only, last 4 digits of the phone only

Optional: with ZINGAS_OS_URL and ZINGAS_OS_TOKEN both set, every do-not-contact
check also asks the website's shared list, and a STOP adds the number to it
(os_link.py). Once an hour the tick also posts this month's text count to the
website's Cost tab (cost_count.py). Without them nothing changes.

Anything that can't be checked fails closed: a missing secret means 401 or 503,
never "let it through".
"""

from __future__ import annotations

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge import Bridge, Config, bearer_ok  # noqa: E402
from clients import ComposioGmail, QuoClient, TelegramClient  # noqa: E402
from cost_count import CostPoster  # noqa: E402
from os_link import OsLink, SharedDncStore, drafts_for_os  # noqa: E402
from store import SupabaseStore  # noqa: E402

MAX_BODY = 64 * 1024
MAX_LIST_BODY = 512 * 1024   # the day's follow-up list (up to 40 texts + emails)
REQUIRED = ("QUO_API_KEY", "QUO_PHONE_NUMBER_ID", "QUO_WEBHOOK_SECRET", "APPROVALS_BOT_TOKEN",
            "APPROVALS_WEBHOOK_SECRET", "APPROVER_TELEGRAM_ID", "VAL_DRAFT_TOKEN", "CRON_SECRET",
            "SUPABASE_URL", "SUPABASE_SERVICE_KEY")

_bridge = None


def build_bridge(env=os.environ) -> Bridge:
    missing = [k for k in REQUIRED if not env.get(k)]
    if missing:
        raise RuntimeError("missing settings: " + ", ".join(missing))   # names only, never values
    # F0 follow-up emails: only once Gerrit has run files/f0-setup.sh. Until then
    # follow-ups send their texts and say the email isn't set up.
    email = (ComposioGmail(env["COMPOSIO_API_KEY"], env["COMPOSIO_GMAIL_ACCOUNT_ID"])
             if env.get("COMPOSIO_API_KEY") and env.get("COMPOSIO_GMAIL_ACCOUNT_ID") else None)
    store = SupabaseStore(env["SUPABASE_URL"], env["SUPABASE_SERVICE_KEY"])
    # The website's shared do-not-contact list and the hourly cost count: only when both settings are there.
    cost = None
    if env.get("ZINGAS_OS_URL") and env.get("ZINGAS_OS_TOKEN"):
        store = SharedDncStore(store, OsLink(env["ZINGAS_OS_URL"], env["ZINGAS_OS_TOKEN"]))
        cost = CostPoster(env["ZINGAS_OS_URL"], env["ZINGAS_OS_TOKEN"])
    return Bridge(Config.from_env(env), store,
                  QuoClient(env["QUO_API_KEY"], env["QUO_PHONE_NUMBER_ID"]),
                  TelegramClient(env["APPROVALS_BOT_TOKEN"]), email=email, cost=cost)


def _headers(environ) -> dict:
    out = {k[5:].replace("_", "-").lower(): v for k, v in environ.items() if k.startswith("HTTP_")}
    if environ.get("CONTENT_TYPE"):
        out["content-type"] = environ["CONTENT_TYPE"]
    return out


def _reply(start_response, status: int, body: dict):
    raw = json.dumps(body).encode()
    names = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found", 405: "Method Not Allowed",
             409: "Conflict", 413: "Payload Too Large", 429: "Too Many Requests", 500: "Internal Server Error",
             503: "Service Unavailable"}
    start_response(f"{status} {names.get(status, 'OK')}",
                   [("Content-Type", "application/json"), ("Content-Length", str(len(raw))),
                    ("Cache-Control", "no-store")])
    return [raw]


def make_app(get_bridge):
    def app(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/").rstrip("/") or "/"
        if path == "/api/health":
            return _reply(start_response, 200, {"ok": True})

        routes = {("POST", "/api/quo"), ("GET", "/api/val/updates"), ("POST", "/api/val/ack"),
                  ("POST", "/api/val/drafts"), ("POST", "/api/telegram"), ("GET", "/api/tick"),
                  ("POST", "/api/val/followups"), ("GET", "/api/val/followups/outcomes"),
                  ("POST", "/api/val/followups/pause"), ("POST", "/api/val/followups/contacts"),
                  ("GET", "/api/os/drafts"), ("POST", "/api/val/activity")}
        if (method, path) not in routes:
            known = {p for _, p in routes}
            return _reply(start_response, 405 if path in known else 404, {"error": "no such door"})

        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if length > (MAX_LIST_BODY if path == "/api/val/followups" else MAX_BODY):
            return _reply(start_response, 413, {"error": "too big"})
        raw = environ["wsgi.input"].read(length) if length > 0 else b""
        headers = _headers(environ)

        try:
            bridge = get_bridge()
        except Exception as e:
            print(f"quo-bridge not set up: {e}", file=sys.stderr)
            return _reply(start_response, 503, {"error": "not set up yet"})

        try:
            if path == "/api/quo":
                status, body = bridge.handle_quo(headers, raw)
            elif path == "/api/telegram":
                status, body = bridge.handle_telegram(headers, raw)
            elif path == "/api/tick":
                if not bearer_ok(headers, bridge.cfg.cron_secret):
                    return _reply(start_response, 401, {"error": "bad code"})
                status, body = bridge.tick()
            elif path == "/api/os/drafts":   # the website's read-only door
                if not bearer_ok(headers, bridge.cfg.os_token):
                    return _reply(start_response, 401, {"error": "bad code"})
                status, body = 200, drafts_for_os(bridge.store)
            else:   # Val's doors
                if not bearer_ok(headers, bridge.cfg.val_token):
                    return _reply(start_response, 401, {"error": "bad code"})
                if path == "/api/val/updates":
                    status, body = bridge.val_updates()
                elif path == "/api/val/followups/outcomes":
                    status, body = bridge.val_followup_outcomes()
                else:
                    try:
                        payload = json.loads(raw or b"{}")
                    except ValueError:
                        return _reply(start_response, 400, {"error": "not json"})
                    if not isinstance(payload, dict):
                        return _reply(start_response, 400, {"error": "send a JSON object"})
                    handler = {"/api/val/ack": bridge.val_ack, "/api/val/drafts": bridge.val_draft,
                               "/api/val/followups": bridge.val_followups,
                               "/api/val/followups/pause": bridge.val_followup_pause,
                               "/api/val/followups/contacts": bridge.val_followup_contacts,
                               "/api/val/activity": bridge.val_activity}[path]
                    status, body = handler(payload)
        except Exception:
            # The trace names files and lines, never settings values.
            traceback.print_exc(file=sys.stderr)
            return _reply(start_response, 500, {"error": "something broke; it's in the Vercel log"})
        return _reply(start_response, status, body)

    return app


def _cached_bridge() -> Bridge:
    global _bridge
    if _bridge is None:
        _bridge = build_bridge()
    return _bridge


app = make_app(_cached_bridge)
