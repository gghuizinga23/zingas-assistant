"""Zinga's Assistant: Quo tells quo-bridge about missed calls (one-time setup, plan F2, SETUP-VAL T6).

Why: Gerrit's tests 2026-10-26 showed Quo never sends quo-bridge "call.completed" for a call nobody answered,
so a missed call made no text-back card. Quo has a separate "call.missed" alert for exactly that.

Run by files/quo-missed-setup.sh on Gerrit's laptop. Two keys arrive on stdin (never argv, never saved, never
printed):
  1. a Vercel token made for this run (delete it after)
  2. QUO_API_KEY (1Password: Zingas Bridge > Bridge Secrets)
It:
  - finds quo-bridge's call alert in Quo ("zingas-bridge-calls", the newest at quo-bridge's address),
  - puts the newest quo-bridge code online first (it reads call.missed) and checks its health,
  - only then adds "call.missed" to that same alert. Same alert, same signing key: no Vercel setting changes.
It texts nobody and changes nothing else. Python standard library only.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # run with python3 -I
import quo_setup as qs  # noqa: E402
from bridge import CALL_EVENTS  # noqa: E402  (quo_setup puts quo-bridge on the path)

LABEL = "zingas-bridge-calls"


def calls_alert(hooks):
    """The newest zingas-bridge-calls alert at quo-bridge's address."""
    ours = [w for w in hooks if w.get("label") == LABEL and str(w.get("url") or "").endswith("/api/quo")]
    if not ours:
        raise qs.Stop(f"Quo has no {LABEL} alert at quo-bridge's address. Nothing was changed. Tell Claude.")
    return max(ours, key=lambda w: str(w.get("createdAt") or ""))


def new_events(hook):
    """The alert's events plus every call event quo-bridge reads now, in a steady order."""
    have = list(hook.get("events") or [])
    return have + [e for e in CALL_EVENTS if e not in have]


def main():
    lines = sys.stdin.read().splitlines()
    if len(lines) < 2 or not all(x.strip() for x in lines[:2]):
        raise qs.Stop("Not everything was pasted. Nothing was changed.")
    vercel_token, quo_key = (x.strip() for x in lines[:2])
    quo = qs.QuoClient(quo_key, "")
    try:
        hook = calls_alert(quo.list_webhooks())
    except qs.QuoError as e:
        raise qs.Stop(f"Quo didn't accept the key: {e} Nothing was changed.")
    events = new_events(hook)
    if events == list(hook.get("events") or []):
        qs.say(f"The {LABEL} alert already has call.missed. Nothing to add.")
    vercel = qs.Vercel(vercel_token)
    st, _ = vercel.call("GET", f"/v9/projects/{qs.NAME}")
    if st != 200:
        raise qs.Stop(f"Vercel has no project {qs.NAME!r} on this team (HTTP {st}). Nothing was changed.")
    qs.say("Putting the newest quo-bridge online (about a minute)...")
    url = vercel.deploy()
    st, _ = qs.http("GET", url + "/api/health")
    if st != 200:
        raise qs.Stop(f"quo-bridge is online but didn't answer its health check (HTTP {st}). The Quo alert "
                      "was not changed. Tell Claude.")
    qs.say(f"quo-bridge is live at {url} and answers.")
    if events != list(hook.get("events") or []):
        quo._call("PATCH", "/webhooks/" + str(hook["id"]), {"events": events})
        check = calls_alert(quo.list_webhooks())
        if "call.missed" not in (check.get("events") or []):
            raise qs.Stop("Quo took the change but the alert still has no call.missed. Tell Claude.")
        qs.say(f"Done: the {LABEL} alert now also tells quo-bridge about missed calls "
               f"({', '.join(check.get('events') or [])}).")
    qs.say("Call the Quo number from your cell and hang up, then tell Claude.")


if __name__ == "__main__":
    try:
        main()
    except qs.Stop as e:
        qs.say(str(e))
        sys.exit(1)
