"""Zinga's Assistant: connect Gerrit's Gmail + Calendar to Composio and make Val's locked session.

Run by files/gmail-setup.sh on Gerrit's laptop. The main Composio key arrives on
stdin (never argv, never saved). It is used here only, on the laptop, to:
  1. make (or reuse) Gmail and Calendar auth configs with narrow Google scopes
  2. open Google's sign-in so Gerrit connects zingashome.com Gmail and Calendar
  3. make a Composio session that allows ONLY the read / search / draft /
     read-calendar tools below, with no workbench, no raw API, no new connections
  4. send the session's link (not the key) to Val's computer

Val reaches the session with her own limited key (COMPOSIO_VAL_KEY in 1Password),
which can only run tools inside a session. Python standard library only.
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

API = "https://backend.composio.dev/api/v3.1"
USER_ID = "gerrit"
ORGO = sys.argv[1] if len(sys.argv) > 1 else "orgo"
COMPUTER = sys.argv[2] if len(sys.argv) > 2 else "Hermes Agent"

G = "https://www.googleapis.com/auth/"
TOOLKITS = {
    # Narrow Google scopes: no delete, trash, labels or calendar changes even if
    # the tool allowlist ever failed. (No Google scope allows drafts without send;
    # the allowlist is what blocks send.)
    "gmail": {
        "name": "Val Gmail (read + draft)",
        "scopes": [G + "gmail.readonly", G + "gmail.compose", G + "userinfo.email"],
        "tools": [
            "GMAIL_FETCH_EMAILS", "GMAIL_LIST_MESSAGES", "GMAIL_LIST_THREADS",
            "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID", "GMAIL_FETCH_MESSAGE_BY_THREAD_ID",
            "GMAIL_CREATE_EMAIL_DRAFT", "GMAIL_LIST_DRAFTS", "GMAIL_GET_DRAFT",
            "GMAIL_GET_ATTACHMENT",
        ],
    },
    "googlecalendar": {
        "name": "Val Calendar (read only)",
        "scopes": [G + "calendar.readonly", G + "userinfo.email"],
        "tools": [
            "GOOGLECALENDAR_EVENTS_LIST", "GOOGLECALENDAR_FIND_EVENT",
            "GOOGLECALENDAR_EVENTS_GET", "GOOGLECALENDAR_LIST_CALENDARS",
            "GOOGLECALENDAR_FREE_BUSY_QUERY",
        ],
    },
}


def call(key, method, path, body=None, query=None):
    url = API + path
    if query:
        url += "?" + "&".join(f"{k}={v}" for k, v in query.items())
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"x-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read()).get("error", {})
            msg = err.get("message") or str(err)
        except Exception:
            msg = e.reason
        raise SystemExit(f"Composio said no ({e.code}) on {method} {path}: {msg}")


def auth_config(key, slug, spec):
    found = call(key, "GET", "/auth_configs", query={"toolkit_slug": slug}) or {}
    for item in found.get("items", []):
        if item.get("name") == spec["name"]:
            return item["id"]
    made = call(key, "POST", "/auth_configs", {
        "toolkit": {"slug": slug},
        "auth_config": {"type": "use_composio_managed_auth", "name": spec["name"],
                        "credentials": {"scopes": ",".join(spec["scopes"])}},
    })
    return made["auth_config"]["id"]


def active_account(key, slug, ac_id):
    res = call(key, "GET", "/connected_accounts", query={
        "user_ids": USER_ID, "toolkit_slugs": slug, "auth_config_ids": ac_id, "statuses": "ACTIVE"}) or {}
    items = res.get("items", [])
    return items[0]["id"] if items else None


def connect(key, slug, ac_id, label):
    ca = active_account(key, slug, ac_id)
    if ca:
        print(f"  {label}: already connected.")
        return ca
    link = call(key, "POST", "/connected_accounts/link", {"auth_config_id": ac_id, "user_id": USER_ID})
    print(f"\n  {label}: a Google sign-in page is opening in your browser.")
    print("  Sign in with your zingashome.com account and click Allow.")
    print("  If no page opens, copy this link into your browser:\n  " + link["redirect_url"])
    webbrowser.open(link["redirect_url"])
    for _ in range(120):  # up to 10 minutes
        time.sleep(5)
        ca = active_account(key, slug, ac_id)
        if ca:
            print(f"  {label}: connected.")
            return ca
    raise SystemExit(f"{label} wasn't connected within 10 minutes. Nothing else was changed. Run this again.")


def main():
    key = sys.stdin.readline().strip()
    if not key:
        raise SystemExit("No key pasted. Nothing was changed.")
    print("Checking the key with Composio...")
    acs, cas = {}, {}
    for slug, spec in TOOLKITS.items():
        acs[slug] = auth_config(key, slug, spec)
    for slug, label in (("gmail", "Gmail"), ("googlecalendar", "Calendar")):
        cas[slug] = connect(key, slug, acs[slug], label)

    every_tool = [t for spec in TOOLKITS.values() for t in spec["tools"]]
    session = call(key, "POST", "/tool_router/session", {
        "user_id": USER_ID,
        "toolkits": {"enable": list(TOOLKITS)},
        "tools": {slug: {"enable": spec["tools"]} for slug, spec in TOOLKITS.items()},
        "auth_configs": acs,
        "connected_accounts": {slug: [ca] for slug, ca in cas.items()},
        "manage_connections": {"enable": False},
        "workbench": {"enable": False},
        "proxy_execute": {"enable": False},
        "preload": {"tools": every_tool},
    })
    url = session["mcp"]["url"]
    print(f"\nLocked session made. Tools Val can reach: {len(every_tool)}")
    for w in session.get("warnings", []):
        print("  note from Composio:", w.get("message"))

    # Only the session link goes to Val's computer; the main key stays here, in memory.
    remote = f"""umask 077
f=/root/.hermes/.env
touch "$f"
grep -v '^COMPOSIO_MAIL_MCP_URL=' "$f" > "$f.tmp" || true
printf 'COMPOSIO_MAIL_MCP_URL=%s\\n' '{url}' >> "$f.tmp"
mv "$f.tmp" "$f"
chmod 600 "$f"
grep -c '^COMPOSIO_MAIL_MCP_URL=' "$f" | sed 's/^/Saved on Val computer: /'
"""
    r = subprocess.run([ORGO, "computers", "bash", COMPUTER], input=remote, text=True,
                       capture_output=True, timeout=180)
    print(r.stdout.strip() or r.stderr.strip())
    print("\nDone. Val can't use it yet: I run the safety tests first.")


if __name__ == "__main__":
    main()
