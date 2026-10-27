"""Zinga's Assistant: what did Quo do with the last calls? (read-only check)

Run by files/quo-check-calls.sh on Gerrit's laptop. The Quo key arrives on stdin (never argv, never saved,
never printed). It only reads from Quo and prints:
  1. quo-bridge's Quo alerts: name, on/off, version, which events (never their signing keys),
  2. the newest call alerts Quo sent to quo-bridge, and how quo-bridge answered each (code and short reply),
  3. the newest calls on the business number: when, direction, status, length (only the last 4 digits of
     the other number).
It changes nothing in Quo, texts nobody and calls nobody.
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # run with python3 -I
import quo_setup as qs  # noqa: E402

CALL_TYPES = ("call.completed", "call.missed", "call.voicemail.completed", "call.summary.completed",
              "call.ringing", "call.answered")


def last4(value) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return "..." + digits[-4:] if len(digits) >= 4 else "?"


def short(value, n: int = 160) -> str:
    return " ".join(str(value or "").split())[:n]


def alerts(quo) -> list:
    hooks = [w for w in quo.list_webhooks() if str(w.get("url") or "").endswith("/api/quo")]
    qs.say(f"quo-bridge's Quo alerts ({len(hooks)}):")
    for w in hooks:
        qs.say(f"  - {w.get('label') or '(no name)'}: {w.get('status')}, version {w.get('apiVersion') or 'old'}, "
               f"made {str(w.get('createdAt') or '?')[:16]}, id {w.get('id')}, events {', '.join(w.get('events') or [])}")
    return hooks


def deliveries(quo, hooks) -> None:
    for w in hooks:
        if not any(e.startswith("call.") for e in (w.get("events") or [])):
            continue
        got = quo._call("GET", f"/webhooks/{urllib.parse.quote(str(w['id']))}/events?limit=12")
        rows = got.get("data") or []
        qs.say(f"\nNewest alerts Quo sent from '{w.get('label')}' ({len(rows)}):")
        for d in rows:
            line = f"  - {str(d.get('createdAt') or '?')[:19]} {d.get('eventType')}: {d.get('status')}, call {d.get('resourceId')}"
            if str(d.get("eventType") or "").startswith("call."):
                try:
                    one = quo._call("GET", f"/webhooks/{urllib.parse.quote(str(w['id']))}/events/"
                                           f"{urllib.parse.quote(str(d.get('id')))}")
                    data = one.get("data") or one
                    sent = data.get("requestBody") or {}
                    if isinstance(sent, str):      # Quo may give the request as text
                        try:
                            sent = json.loads(sent)
                        except ValueError:
                            sent = {}
                    res = ((sent.get("data") or sent).get("resource") or {}) if isinstance(sent, dict) else {}
                    tries = data.get("attempts") or []
                    t = tries[-1] if tries else {}
                    bits = [f"{k} {res[k]!r}" for k in ("direction", "status", "duration", "hasVoicemail",
                                                         "handledByAiAgent", "processingStatus") if k in res]
                    line += (f"\n      Quo said: {', '.join(bits) or '(no details)'}"
                             f"\n      quo-bridge answered: {t.get('responseStatusCode')} {short(t.get('responseBody'))}")
                except qs.QuoError as e:
                    line += f"\n      (details: {e})"
            qs.say(line)


def calls(quo) -> None:
    number_id = qs.quo_number(quo)
    got = quo._call("GET", f"/calls?phoneNumberId={urllib.parse.quote(number_id)}&limit=6")
    rows = got.get("data") or []
    qs.say(f"\nNewest calls on the business number ({len(rows)}):")
    for c in rows:
        others = [p.get("phoneNumber") for p in (c.get("participants") or []) if p.get("phoneNumber")]
        qs.say(f"  - {str(c.get('createdAt') or '?')[:19]} id {c.get('id')}: {c.get('direction')}, "
               f"status {c.get('status')}, {c.get('duration')} s, answered {'yes' if c.get('answeredAt') else 'no'}, "
               f"numbers {', '.join(last4(x) for x in others) or '?'}")


def main():
    lines = sys.stdin.read().splitlines()
    if not lines or not lines[0].strip():
        raise qs.Stop("Nothing was pasted. Nothing was read.")
    quo = qs.QuoClient(lines[0].strip(), "")
    hooks = alerts(quo)
    for step in (lambda: deliveries(quo, hooks), lambda: calls(quo)):
        try:
            step()
        except (qs.QuoError, qs.Stop) as e:
            qs.say(f"(Quo refused one of the reads: {e})")
    qs.say("\nDone. Nothing was changed. Tell Claude.")


if __name__ == "__main__":
    try:
        main()
    except qs.Stop as e:
        qs.say(str(e))
        sys.exit(1)
