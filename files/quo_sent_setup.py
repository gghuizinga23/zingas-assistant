"""Zinga's Assistant: Quo tells quo-bridge about texts Gerrit sends himself (one-time setup).

Why: when Gerrit answers a customer himself in the Quo app, quo-bridge must know, so Val's waiting draft to
that person stops (no second answer) and Val learns from what he wrote (files/zingas_voice.py).

Run by files/quo-sent-setup.sh on Gerrit's laptop, AFTER the quo-bridge code that reads these alerts is online
(files/quo-redeploy.sh). Two keys arrive on stdin (never argv, never saved, never printed):
  1. QUO_API_KEY   (1Password: Zingas Bridge > Bridge Secrets)
  2. a Vercel token made for this run (delete it after)
It:
  - makes three new Quo alerts to the same quo-bridge address: new texts, calls, and sent texts
    ("message.delivered"),
  - saves their three signing keys in Vercel (QUO_WEBHOOK_SECRET) and puts quo-bridge online again,
  - only then removes the old alerts. Old and new overlap for a minute, so no text is missed; a text that
    comes in twice is kept once.
It texts nobody and changes no other setting. Python standard library only.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # run with python3 -I
import quo_setup as qs  # noqa: E402
from bridge import CALL_EVENTS, SENT_EVENTS  # noqa: E402  (quo_setup puts quo-bridge on the path)

LABELS = ("zingas-bridge", "zingas-bridge-calls", "zingas-bridge-sent")


def plan(hooks):
    """The quo-bridge address and the old alerts to remove, from Quo's list of alerts."""
    old = [w for w in hooks if w.get("label") in LABELS or str(w.get("url") or "").endswith("/api/quo")]
    urls = sorted({w.get("url") for w in old if str(w.get("url") or "").endswith("/api/quo")})
    if len(urls) != 1:
        raise qs.Stop(f"Expected one quo-bridge alert address in Quo, found {len(urls)}. Nothing was changed. "
                      "Tell Claude.")
    return urls[0], old


def main():
    lines = sys.stdin.read().splitlines()
    if len(lines) < 2 or not all(x.strip() for x in lines[:2]):
        raise qs.Stop("Not everything was pasted. Nothing was changed.")
    quo_key, vercel_token = (x.strip() for x in lines[:2])
    vercel = qs.Vercel(vercel_token)
    st, _ = vercel.call("GET", f"/v9/projects/{qs.NAME}")
    if st != 200:
        raise qs.Stop(f"Vercel has no project {qs.NAME!r} on this team (HTTP {st}). Nothing was changed.")
    quo = qs.QuoClient(quo_key, "")
    number_id = qs.quo_number(quo)
    url, old = plan(quo.list_webhooks())
    qs.say(f"quo-bridge's alert address: {url} ({len(old)} old alert(s) there now)")

    keys = []
    for events, label in (((("message.received",)), "zingas-bridge"), (CALL_EVENTS, "zingas-bridge-calls"),
                          (SENT_EVENTS, "zingas-bridge-sent")):
        hook = quo.create_webhook(url, number_id, events=events, label=label)
        if not hook.get("key"):
            raise qs.Stop(f"Quo made the {label} alert but gave no signing key. The old alerts still work. "
                          "Tell Claude.")
        keys.append(hook["key"])
        qs.say(f"Made the {label} alert.")
    vercel.set_env({"QUO_WEBHOOK_SECRET": ",".join(keys)})
    qs.say("Saved the new keys. Putting quo-bridge online with them (about a minute)...")
    live = vercel.deploy()
    st, _ = qs.http("GET", live + "/api/health")
    if st != 200:
        raise qs.Stop(f"quo-bridge is online but didn't answer its health check (HTTP {st}). Tell Claude.")
    for w in old:
        quo.delete_webhook(w["id"])
    qs.say(f"Removed {len(old)} old alert(s). Done: quo-bridge now hears about texts you send in the Quo app.")


if __name__ == "__main__":
    try:
        main()
    except qs.Stop as e:
        qs.say(str(e))
        sys.exit(1)
