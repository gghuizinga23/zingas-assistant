"""Gmail part G4: live safety checks. Runs ON Val's computer (files/gmail-safety-check.sh
sends it there) with Val's own limited Composio key. Prints OK/FAIL lines and short
reasons only, never a key, a link or any email text.

Every "must be refused" try is aimed so that nothing real can happen even if it
were allowed: the send goes to test@example.com (a domain that takes no mail) and
the delete uses a made-up message ID.
"""
import json
import os
import re
import subprocess
import urllib.error
import urllib.request

API = "https://backend.composio.dev/api/v3.1"
ENV = "/root/.hermes/.env"
OP_ENV = "/root/.hermes/.op.env"
results = []


def check(name, ok, why=""):
    results.append(ok)
    print(("OK   " if ok else "FAIL ") + name + (f"  [{why}]" if why else ""), flush=True)


def scrub(text):
    text = re.sub(r"(ak_|sk_|lk_|https?://)\S+", "<hidden>", str(text))
    return " ".join(text.split())[:140]


def env_value(path, name):
    try:
        with open(path) as fh:
            for line in fh:
                if line.startswith(name + "="):
                    return line.strip().split("=", 1)[1]
    except OSError:
        pass
    return ""


url = env_value(ENV, "COMPOSIO_MAIL_MCP_URL")
op_env = dict(os.environ, OP_SERVICE_ACCOUNT_TOKEN=env_value(OP_ENV, "OP_SERVICE_ACCOUNT_TOKEN"))
key = subprocess.run(["op", "read", "op://Zingas Assistant/Assistant Secrets/COMPOSIO_VAL_KEY"],
                     capture_output=True, text=True, env=op_env).stdout.strip()
check("Val has the locked Gmail link and her own limited key", url.startswith("https://") and bool(key))


def http(method, target, body=None, headers=None):
    req = urllib.request.Request(target, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"x-api-key": key, "Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode(errors="replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace"), dict(e.headers)
    except urllib.error.URLError as e:
        return 0, str(e.reason), {}


# ---- the locked session (MCP) ----
session_id = None
next_id = 0


def mcp(method, params=None, notify=False):
    global session_id, next_id
    msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if not notify:
        next_id += 1
        msg["id"] = next_id
    h = {"Accept": "application/json, text/event-stream"}
    if session_id:
        h["mcp-session-id"] = session_id
    status, text, headers = http("POST", url, msg, h)
    session_id = session_id or {k.lower(): v for k, v in headers.items()}.get("mcp-session-id")
    if notify:
        return status, None
    for line in text.splitlines():          # answers may come as server-sent events
        if line.startswith("data:"):
            text = line[5:].strip()
    try:
        return status, json.loads(text)
    except ValueError:
        return status, {"error": {"message": text}}


def call(tool, args):
    """Returns (worked, reason). 'worked' means the tool really ran."""
    status, out = mcp("tools/call", {"name": tool, "arguments": args})
    if "error" in out:
        return False, scrub(out["error"].get("message", out["error"]))
    res = out.get("result", {})
    text = " ".join(c.get("text", "") for c in res.get("content", []) if isinstance(c, dict))
    if res.get("isError"):
        return False, scrub(text)
    try:
        data = json.loads(text)
    except ValueError:
        data = {}
    if isinstance(data, dict) and (data.get("successful") is False or data.get("error")):
        return False, scrub(data.get("error") or text)
    # a meta tool that wraps other tools reports each one inside "data"
    inner = json.dumps(data.get("data", "")) if isinstance(data, dict) else ""
    if re.search(r'"successful":\s*false|"error":\s*"[^"]', inner):
        return False, scrub(inner)
    return True, scrub(text)


st, init = mcp("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                              "clientInfo": {"name": "val-safety-check", "version": "1"}})
check("the locked link opens with Val's key", st == 200 and "result" in init, f"HTTP {st}")
mcp("notifications/initialized", notify=True)
st, listing = mcp("tools/list")
names = sorted(t.get("name", "") for t in listing.get("result", {}).get("tools", []))
print("     tools Val sees: " + ", ".join(names))
risky = [n for n in names if re.search(r"SEND|DELETE|TRASH|MODIFY|LABEL|FORWARD|REPLY|WORKBENCH|BASH|"
                                        r"MANAGE_CONNECTION|PROXY|CALENDAR.*(CREATE|UPDATE|DELETE|PATCH)", n)]
check("no send, delete, forward, workbench or connection tools in the list", not risky, ", ".join(risky))

worked, why = call("GMAIL_LIST_DRAFTS", {"max_results": 1})
check("an allowed tool works (list drafts)", worked, "" if worked else why)

SEND = {"recipient_email": "test@example.com", "subject": "Val safety test", "body": "This must not send."}
tries = [
    ("send an email", "GMAIL_SEND_EMAIL", SEND),
    ("send a draft", "GMAIL_SEND_DRAFT", {"draft_id": "r-0000000000000000000"}),
    ("reply to a thread", "GMAIL_REPLY_TO_THREAD", {"thread_id": "0000000000000000", **SEND}),
    ("forward an email", "GMAIL_FORWARD_MESSAGE", {"message_id": "0000000000000000", "recipient_email": "test@example.com"}),
    ("delete an email", "GMAIL_DELETE_MESSAGE", {"message_id": "0000000000000000"}),
    ("trash an email", "GMAIL_MOVE_TO_TRASH", {"message_id": "0000000000000000"}),
    ("add a new connection", "COMPOSIO_MANAGE_CONNECTIONS", {"toolkits": ["gmail"]}),
    ("run code in the workbench", "COMPOSIO_REMOTE_WORKBENCH", {"code_to_execute": "print(1)"}),
    ("send through the multi-tool runner", "COMPOSIO_MULTI_EXECUTE_TOOL",
     {"tools": [{"tool_slug": "GMAIL_SEND_EMAIL", "arguments": SEND}], "sync_response_to_workbench": False}),
]
for label, tool, args in tries:
    worked, why = call(tool, args)
    check(f"Val can't {label}", not worked, why)

# ---- Val's key straight against Composio, outside the session ----
st, text, _ = http("POST", API + "/tool_router/session", {"user_id": "gerrit", "toolkits": {"enable": ["gmail"]}})
check("Val's key can't make a new session", st in (401, 403), f"HTTP {st}: {scrub(text)}")
st, text, _ = http("POST", API + "/tools/execute/GMAIL_SEND_EMAIL", {"user_id": "gerrit", "arguments": SEND})
check("Val's key can't run send directly", st in (401, 403), f"HTTP {st}: {scrub(text)}")
st, text, _ = http("GET", API + "/connected_accounts")
check("Val's key can't list or reach accounts", st in (401, 403), f"HTTP {st}: {scrub(text)}")

# ---- no other tool server on Val's computer that can send (Orgo's own one can) ----
r = subprocess.run(["/usr/local/lib/hermes-agent/venv/bin/python", "-c",
                    "import yaml,json;c=yaml.safe_load(open('/root/.hermes/config.yaml'));"
                    "print(json.dumps(sorted(k for k,v in (c.get('mcp_servers') or {}).items() "
                    "if (v or {}).get('enabled', True) is not False)))"], capture_output=True, text=True)
on = json.loads(r.stdout or "null")
check("only the gmail and notes-vault tool servers are on", on is not None and set(on) <= {"gmail", "obsidian-vault"},
      ", ".join(on or []) or scrub(r.stderr))

print(f"\n{sum(results)} of {len(results)} checks passed.")
