"""Zinga's Assistant: turn on F0 quote follow-ups.

Run by files/f0-setup.sh on Gerrit's laptop. Two keys arrive on stdin (never
argv, never saved, never printed):
  1. COMPOSIO_API_KEY   the Composio main key (1Password: Zingas Bridge > Bridge Secrets)
  2. a Vercel token     (made for this run; delete it after)
Supabase uses the Supabase app already signed in on this laptop.

What it does, in order (safe to run again):
  - finds Gerrit's Gmail connection in Composio ("Val Gmail (read + draft)", user gerrit)
    and checks the key can read his Sent mail with it (it reads one search, sends nothing)
  - adds the follow-up columns and the batches table to quo-bridge's Supabase (schema-f0.sql)
  - puts the Composio key and the Gmail connection id in quo-bridge's locked Vercel
    settings and puts the new quo-bridge online
  - checks the follow-up doors from outside, and from Val's computer with her drafts-only code
  - turns F0 on in Val's vault (the LIVE file); her program posts the first list on the
    next weekday at 8:01 AM

Val's computer never gets the Composio main key. Nothing here sends a text or an email.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import quo_setup as qs  # noqa: E402  (its Vercel, Supabase and http helpers)
from quo_setup import Stop, say  # noqa: E402

COMPOSIO = "https://backend.composio.dev/api/v3.1"
AUTH_NAME = "Val Gmail (read + draft)"
USER_ID = "gerrit"
F0_TABLES = qs.VAL_TABLES | {"batches"}


def composio(key, method, path, body=None, query=None):
    url = COMPOSIO + path + ("?" + urllib.parse.urlencode(query) if query else "")
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"x-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise Stop(f"Composio said no (HTTP {e.code}) on {path.split('?')[0]}. Check you pasted the main key.")
    except (urllib.error.URLError, OSError) as e:
        raise Stop(f"No answer from Composio ({type(e).__name__}). Run this again.")


def gmail_account(key):
    configs = composio(key, "GET", "/auth_configs", query={"toolkit_slug": "gmail"}).get("items") or []
    ac = next((c for c in configs if c.get("name") == AUTH_NAME), None)
    if not ac:
        raise Stop(f"Composio has no '{AUTH_NAME}' setup. Run files/gmail-setup.sh first.")
    accounts = composio(key, "GET", "/connected_accounts", query={
        "user_ids": USER_ID, "toolkit_slugs": "gmail", "auth_config_ids": ac["id"], "statuses": "ACTIVE"}).get("items") or []
    if not accounts:
        raise Stop("Gerrit's Gmail is not connected in Composio. Run files/gmail-setup.sh first.")
    account = accounts[0]["id"]
    out = composio(key, "POST", "/tools/execute/GMAIL_FETCH_EMAILS", {
        "connected_account_id": account, "user_id": USER_ID,
        "arguments": {"query": "in:sent subject:estimate", "max_results": 1, "verbose": False}})
    if not out.get("successful", True) or "messages" not in (out.get("data") or {}):
        raise Stop("Composio found the Gmail connection but could not read Sent mail with it. Tell Claude.")
    say("Composio: Gmail connection found, and it can read Sent mail.")
    return account


def supabase_f0():
    projects = qs.sb("projects", "list")
    proj = next((p for p in projects if p.get("name") == qs.NAME), None)
    if not proj:
        orgs = {o["id"]: o.get("name") for o in qs.sb("orgs", "list")}
        mine = [p for p in projects if orgs.get(p.get("organization_id")) == "Zingas Assistant"]
        if len(mine) != 1:
            raise Stop("Couldn't tell which Supabase project quo-bridge uses. Tell Claude.")
        proj = mine[0]
    ref = proj.get("ref") or proj["id"]
    work = tempfile.mkdtemp(prefix="zingas-sb-")
    try:
        qs.sb("link", "--project-ref", ref, "--workdir", work, raw=True)
        have = {t.get("table_name") for t in qs.sb("db", "query", "--linked", "--workdir", work,
                "select table_name from information_schema.tables where table_schema = 'public'")}
        if not {"drafts", "messages"} <= have:
            raise Stop("That Supabase project doesn't have quo-bridge's tables. Tell Claude.")
        if have - F0_TABLES:
            raise Stop(f"That Supabase project has other tables ({', '.join(sorted(have - F0_TABLES)[:5])}). "
                       "Nothing was added. Tell Claude.")
        qs.sb("db", "query", "--linked", "--workdir", work, "-f", os.path.join(qs.BRIDGE_DIR, "schema-f0.sql"),
              timeout=300)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    say("Supabase: follow-up columns and the batches table are in.")


def check_outside(url):
    def code(method, path, body=None):
        return qs.http(method, url + path, body)[0]
    results = {
        "helper is up": code("GET", "/api/health") == 200,
        "no code, no follow-up list": code("POST", "/api/val/followups", {"day": "2026-01-01", "items": []}) == 401,
        "no code, no outcomes": code("GET", "/api/val/followups/outcomes") == 401,
        "no code, no text history": code("POST", "/api/val/followups/contacts", {"phones": []}) == 401,
    }
    for name, ok in results.items():
        say(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if not all(results.values()):
        raise Stop("A lock check failed. F0 was NOT turned on. Tell Claude.")


VAL_SCRIPT = r"""
set -e
. /root/.hermes/quo-bridge.env
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
a=$(code -H "Authorization: Bearer $VAL_DRAFT_TOKEN" "$QUO_BRIDGE_URL/api/val/followups/outcomes")
b=$(code -H "Authorization: Bearer $VAL_DRAFT_TOKEN" "$QUO_BRIDGE_URL/api/tick")
[ "$a" = 200 ] && echo "  OK   Val's code opens the follow-up door" || { echo "  FAIL Val's code opens the follow-up door ($a)"; exit 1; }
[ "$b" = 401 ] && echo "  OK   Val's code can't run the timer" || { echo "  FAIL Val's code can't run the timer ($b)"; exit 1; }
supervisorctl status zingas-followups | awk '{print "  Val follow-up program:", $2}'
mkdir -p /root/Documents/ZingasVault/followups && chmod 700 /root/Documents/ZingasVault/followups
touch /root/Documents/ZingasVault/followups/LIVE
zingas-followups status | grep -E '"live"|plan_day'
"""


def main():
    lines = sys.stdin.read().splitlines()
    if len(lines) < 2:
        raise Stop("Two keys are needed. Nothing was changed.")
    composio_key, vercel_token = (x.strip() for x in lines[:2])
    account = gmail_account(composio_key)
    vercel = qs.Vercel(vercel_token)
    supabase_f0()
    vercel.project()
    vercel.set_env({"COMPOSIO_API_KEY": composio_key, "COMPOSIO_GMAIL_ACCOUNT_ID": account})
    say("Putting the new quo-bridge online (about a minute)...")
    url = vercel.deploy()
    say("Checking the locks from outside:")
    check_outside(url)
    say("Checking from Val's computer and turning F0 on:")
    r = subprocess.run([qs.ORGO, "computers", "bash", qs.COMPUTER], input=VAL_SCRIPT, text=True,
                       capture_output=True, timeout=180)
    say((r.stdout or "").strip() or "(no answer from Val's computer)")
    if r.returncode != 0 or "FAIL" in (r.stdout or ""):
        raise Stop("Val's computer didn't pass. F0 is NOT on. Tell Claude.")
    say("\nDone. F0 is on. The first follow-up list comes in the next weekday's 8:00 AM brief, "
        "and the Approve all card in Val Approvals at 8:01.\n"
        "Next: delete the Vercel token you made for this (it's not needed again).")


if __name__ == "__main__":
    try:
        main()
    except Stop as e:
        say(f"\nStopped: {e}")
        sys.exit(1)
