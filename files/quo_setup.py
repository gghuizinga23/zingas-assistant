"""Zinga's Assistant: Quo part Q5. Puts quo-bridge online and connects everything.

Run by files/quo-setup.sh on Gerrit's laptop. Three keys arrive on stdin (never
argv, never saved, never printed), then Gerrit's cell number:
  1. QUO_API_KEY            (1Password: Zingas Bridge > Bridge Secrets)
  2. APPROVALS_BOT_TOKEN    (same note)
  3. a Vercel token         (made for this run; delete it after)
  4. Gerrit's cell          (for the 10-minute "a text is waiting" alert)
Supabase uses the Supabase app already signed in on this laptop, not a token
(Gerrit's choice, 2026-10-22).

What it does, in order (safe to run again; it reuses what's already there):
  - checks the Quo key and finds the business number's id
  - finds Gerrit's Telegram id from the Val Approvals bot
  - makes a free Supabase project "zingas-quo-bridge" (or reuses it) and its tables
  - makes three new random codes: Val's drafts-only code, the timer's code,
    and the Telegram door's code
  - makes the Vercel project "zingas-quo-bridge" (or reuses it), puts every key in
    its locked settings, and puts quo-bridge online
  - connects Quo's "new text" alert and the Val Approvals bot to it
  - checks the locks from outside
  - gives Val's computer ONLY the helper's address and her drafts-only code, and
    starts her pickup program

Nothing here sends a text to anyone. Python standard library only.
"""
import base64
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE_DIR = os.path.join(HERE, "..", "quo-bridge")
sys.path.insert(0, BRIDGE_DIR)
import clients  # noqa: E402
from clients import QuoError, TelegramClient, TelegramError  # noqa: E402
from bridge import CALL_EVENTS  # noqa: E402


class QuoClient(clients.QuoClient):
    """Same as the helper's QuoClient, but talks to Quo through curl.

    The Mac's built-in Python 3.9 has LibreSSL 2.8.3 with no TLS 1.3, and Quo's API
    refuses it (TLSV1_ALERT_PROTOCOL_VERSION). The Mac's curl connects fine. The key
    goes to curl on stdin as a config line, never on the command line."""

    def _call(self, method, path, body=None, versioned=True):
        cfg = ['header = "Authorization: %s"' % self.api_key.replace("\\", "\\\\").replace('"', '\\"'),
               'header = "Accept: application/json"']
        if versioned:
            cfg.append('header = "Quo-Api-Version: %s"' % clients.QUO_API_VERSION)
        if body is not None:
            data = json.dumps(body).replace("\\", "\\\\").replace('"', '\\"')
            cfg += ['header = "Content-Type: application/json"', 'data-binary = "%s"' % data]
        out = subprocess.run(
            ["curl", "-sS", "-X", method, "--max-time", str(int(self.timeout)), "-K", "-",
             "-w", "\n%{http_code}", clients.QUO_API + path],
            input="\n".join(cfg) + "\n", capture_output=True, text=True)
        raw, _, status = out.stdout.rpartition("\n")
        if out.returncode != 0 or not status.isdigit() or status == "000":
            raise QuoError("No answer from Quo (curl).", unknown=True)
        if int(status) >= 400:
            code = int(status)
            raise QuoError(clients._QUO_REASONS.get(code, f"Quo error {code}."), status=code)
        return json.loads(raw) if raw.strip() else {}

ORGO = sys.argv[1] if len(sys.argv) > 1 else "orgo"
COMPUTER = sys.argv[2] if len(sys.argv) > 2 else "Hermes Agent"
NAME = "zingas-quo-bridge"
DEPLOY_FILES = ("app.py", "bridge.py", "clients.py", "store.py", "send_gate.py", "pyproject.toml", "vercel.json")
VAL_FILES = {   # laptop file -> place on Val's computer
    "quo_pickup.py": "/usr/local/bin/zingas-quo",
    "quo-pickup.supervisor.conf": "/etc/supervisor/conf.d/zingas-quo-pickup.conf",
    "skills/zingas/quo-texting/SKILL.md": "/root/.hermes/skills/zingas/quo-texting/SKILL.md",
    "zingas_todo.py": "/usr/local/lib/zingas/zingas_todo.py",      # the to-do list the pickup adds to
    "skills/zingas/todo-list/SKILL.md": "/root/.hermes/skills/zingas/todo-list/SKILL.md",
}


class Stop(Exception):
    pass


def say(msg=""):
    print(msg, flush=True)


def ask(prompt):
    with open("/dev/tty") as tty:
        sys.stdout.write(prompt)
        sys.stdout.flush()
        return tty.readline().strip()


def http(method, url, body=None, headers=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:300].decode(errors="replace")}


def us_phone(value):
    d = re.sub(r"\D", "", value or "")
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return "+1" + d if len(d) == 10 else None


# ---------------------------------------------------------------- Quo + Telegram

def quo_number(quo, cell=None):
    try:
        numbers = quo.list_numbers()
    except QuoError as e:
        raise Stop(f"Quo didn't accept the key: {e}")
    if not numbers:
        raise Stop("Quo shows no phone numbers on this key's workspace.")
    if len(numbers) == 1:
        n = numbers[0]
    else:
        for i, n in enumerate(numbers, 1):
            say(f"  {i}. {n.get('phoneNumber')} {n.get('name') or ''}")
        n = numbers[int(ask("Which one is the business number customers text? Type its number: ")) - 1]
    say(f"Quo business number: {n.get('phoneNumber')}")
    if cell and us_phone(n.get("phoneNumber")) == cell:
        raise Stop("That cell number is the Quo business number. The 'a text is waiting' alert goes from\n"
                   "the Quo number to your own cell, so type your personal cell. Nothing was changed.")
    return n["id"]


def approver_id(tg):
    try:
        me = tg.call("getMe", {})
    except TelegramError as e:
        raise Stop(f"Telegram didn't accept the bot token: {e}")
    say(f"Approvals bot: @{me.get('username')}")
    tg.call("deleteWebhook", {"drop_pending_updates": False})   # getUpdates only works without one
    for attempt in range(2):
        people = {}
        for u in tg.call("getUpdates", {"timeout": 0, "allowed_updates": ["message"]}) or []:
            m = u.get("message") or {}
            if (m.get("chat") or {}).get("type") == "private" and m.get("from"):
                people[m["from"]["id"]] = m["from"].get("first_name", "")
        if len(people) == 1:
            pid, first = next(iter(people.items()))
            if ask(f"Is {first} your Telegram name? Type y or n: ").lower().startswith("y"):
                return int(pid)
            raise Stop("Someone else wrote to the bot. Nothing was changed. Tell Claude.")
        if len(people) > 1:
            raise Stop("More than one person wrote to the bot. Nothing was changed. Tell Claude.")
        if attempt == 0:
            ask(f"Open @{me.get('username')} in Telegram, send it the word hi, then press Return here: ")
    raise Stop("I didn't see your hi in the bot. Nothing was changed. Try again.")


# ---------------------------------------------------------------- Supabase

SUPABASE_CLI = shutil.which("supabase") or "/opt/homebrew/bin/supabase"
VAL_TABLES = {"messages", "drafts", "calls", "contacts", "auto_send_stats", "events"}


def sb(*args, raw=False, timeout=180):
    """Run the Supabase app that is signed in on this laptop. Gerrit chose this
    (2026-10-22) over pasting a Supabase token. Its output is never printed."""
    try:
        r = subprocess.run([SUPABASE_CLI, *args, "--agent", "no"] + ([] if raw else ["-o", "json"]),
                           capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise Stop("The Supabase app isn't on this laptop (brew install supabase/tap/supabase). Tell Claude.")
    except subprocess.TimeoutExpired:
        raise Stop(f"The Supabase app didn't answer in time ({args[0]} {args[1] if len(args) > 1 else ''}). Run this again.")
    if r.returncode != 0:
        err = [ln.strip() for ln in re.sub(r"\x1b\[[0-9;]*m", "", r.stderr or "").splitlines()
               if ln.strip() and not ln.startswith("Try rerunning")][-1:] or ["no message"]
        if "login" in err[0].lower() or "access token" in err[0].lower():
            raise Stop("The Supabase app on this laptop isn't signed in. Run: supabase login   then run this again.")
        raise Stop(f"The Supabase app refused '{' '.join(args[:2])}': {err[0][:200]}")
    if raw:
        return r.stdout
    out = r.stdout
    start = min([i for i in (out.find("["), out.find("{")) if i >= 0], default=-1)
    try:
        return json.loads(out[start:]) if start >= 0 else []
    except ValueError:
        raise Stop(f"The Supabase app gave an answer I couldn't read ('{' '.join(args[:2])}'). Tell Claude.")


def supabase():
    projects = sb("projects", "list")
    proj = next((p for p in projects if p.get("name") == NAME), None)
    if not proj:
        orgs = sb("orgs", "list")
        if not orgs:
            raise Stop("The Supabase app shows no organization. Tell Claude.")
        # Val's texts live in their own organization, apart from the dashboard's.
        org = next((o for o in orgs if o.get("name") == "Zingas Assistant"), None)
        if not org:
            if len(orgs) == 1:
                org = orgs[0]
            else:
                for i, o in enumerate(orgs, 1):
                    say(f"  {i}. {o.get('name')}")
                org = orgs[int(ask("Which Supabase organization is for Val's texts? Type its number: ")) - 1]
        # The free plan allows 2 active projects per owner, so reuse a project already in
        # Val's organization (Supabase made one when the organization was made). Its tables
        # are checked below before anything is added.
        in_org = [p for p in projects if p.get("organization_id") == org["id"]]
        if in_org:
            proj = in_org[0]
            if len(in_org) > 1:
                for i, p in enumerate(in_org, 1):
                    say(f"  {i}. {p.get('name')}")
                proj = in_org[int(ask("Which Supabase project is for Val's texts? Type its number: ")) - 1]
            say(f"Using the Supabase project '{proj.get('name')}' in {org.get('name')}.")
        else:
            say(f"Making a free Supabase project {NAME} in {org.get('name')} (takes about 2 minutes)...")
            sb("projects", "create", NAME, "--org-id", org["id"], "--region", "us-east-2",
               "--db-password", secrets.token_urlsafe(24), raw=True)
            proj = next((p for p in sb("projects", "list") if p.get("name") == NAME), None)
            if not proj:
                raise Stop("Supabase said it made the project, but it isn't in the list. Run this again in a minute.")
    ref = proj.get("ref") or proj["id"]
    for _ in range(80):
        p = next((p for p in sb("projects", "list") if (p.get("ref") or p.get("id")) == ref), {})
        if p.get("status") == "ACTIVE_HEALTHY":
            break
        time.sleep(6)
    else:
        raise Stop("The Supabase project didn't finish starting. Run this again in a few minutes.")
    work = tempfile.mkdtemp(prefix="zingas-sb-")
    try:
        sb("link", "--project-ref", ref, "--workdir", work, raw=True)
        have = sb("db", "query", "--linked", "--workdir", work,
                  "select table_name from information_schema.tables where table_schema = 'public'")
        other = sorted({t.get("table_name") for t in have} - VAL_TABLES)
        if other:
            raise Stop(f"That Supabase project already has other tables ({', '.join(other[:5])}). "
                       "Nothing was added. Tell Claude.")
        sb("db", "query", "--linked", "--workdir", work, "-f", os.path.join(BRIDGE_DIR, "schema.sql"), timeout=300)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    keys = sb("projects", "api-keys", "--project-ref", ref, "--reveal")
    key = next((k["api_key"] for k in keys if k.get("type") == "secret" and k.get("api_key")), None) \
        or next((k["api_key"] for k in keys if k.get("name") == "service_role" and k.get("api_key")), None)
    if not key:
        raise Stop("Couldn't read the Supabase server key.")
    say("Supabase project ready, tables made: messages, drafts, calls, contacts, auto_send_stats, events")
    return f"https://{ref}.supabase.co", key


# ---------------------------------------------------------------- Vercel

class Vercel:
    def __init__(self, token):
        self.hdr = {"Authorization": "Bearer " + token}
        st, out = http("GET", "https://api.vercel.com/v2/teams", headers=self.hdr)
        if st != 200:
            raise Stop(f"Vercel didn't accept the token (HTTP {st}).")
        teams = out.get("teams") or []
        if not teams:
            raise Stop("Vercel shows no team on this token. Make the token for your Pro team.")
        team = teams[0]
        if len(teams) > 1:
            for i, t in enumerate(teams, 1):
                say(f"  {i}. {t.get('name')}")
            team = teams[int(ask("Which Vercel team (the Pro one)? Type its number: ")) - 1]
        self.team = team["id"]
        say(f"Vercel team: {team.get('name')}")

    def call(self, method, path, body=None, timeout=120):
        sep = "&" if "?" in path else "?"
        return http(method, f"https://api.vercel.com{path}{sep}teamId={self.team}", body, self.hdr, timeout)

    def project(self):
        st, p = self.call("GET", f"/v9/projects/{NAME}")
        if st == 404:
            st, p = self.call("POST", "/v11/projects", {"name": NAME, "framework": "python"})
        if st not in (200, 201):
            raise Stop(f"Couldn't make the Vercel project (HTTP {st}).")
        return p

    def set_env(self, values):
        body = [{"key": k, "value": v, "type": "sensitive", "target": ["production"]} for k, v in values.items()]
        st, out = self.call("POST", f"/v10/projects/{NAME}/env?upsert=true", body)
        if st not in (200, 201) or out.get("failed"):
            raise Stop(f"Couldn't save the settings in Vercel (HTTP {st}).")

    def deploy(self):
        files = []
        for f in DEPLOY_FILES:
            with open(os.path.join(BRIDGE_DIR, f), "rb") as fh:
                files.append({"file": f, "data": base64.b64encode(fh.read()).decode(), "encoding": "base64"})
        st, d = self.call("POST", "/v13/deployments?skipAutoDetectionConfirmation=1", {
            "name": NAME, "project": NAME, "target": "production", "files": files,
            "projectSettings": {"framework": "python"}})
        if st not in (200, 201):
            raise Stop(f"Vercel didn't take the upload (HTTP {st}): {d.get('error', {}).get('message', '')}")
        for _ in range(100):
            st, d = self.call("GET", f"/v13/deployments/{d['id']}")
            if d.get("readyState") in ("READY", "ERROR", "CANCELED"):
                break
            time.sleep(5)
        if d.get("readyState") != "READY":
            raise Stop(f"Vercel couldn't build it ({d.get('readyState')}). Tell Claude; nothing is live.")
        aliases = sorted((a for a in d.get("alias") or [] if a.endswith(".vercel.app")), key=len)
        if not aliases:
            st, doms = self.call("GET", f"/v9/projects/{NAME}/domains")
            aliases = sorted((x["name"] for x in doms.get("domains") or [] if x["name"].endswith(".vercel.app")), key=len)
        if not aliases:
            raise Stop("Vercel didn't give the helper an address. Tell Claude.")
        return "https://" + aliases[0]


# ---------------------------------------------------------------- checks + Val

def check_locks(url, val_token, cron):
    def code(method, path, token=None, body=None):
        return http(method, url + path, body, {"Authorization": "Bearer " + token} if token else None)[0]
    results = {
        "helper is up": code("GET", "/api/health") == 200,
        "Val's code opens her door": code("GET", "/api/val/updates", val_token) == 200,
        "no code, no entry": code("GET", "/api/val/updates") == 401,
        "a fake Quo alert is refused": code("POST", "/api/quo", body={"type": "message.received"}) == 401,
        "Val's code can't run the timer": code("GET", "/api/tick", val_token) == 401,
        "a fake Telegram tap is refused": code("POST", "/api/telegram", val_token, {}) == 401,
        "the timer's code works": code("GET", "/api/tick", cron) == 200,
    }
    for name, ok in results.items():
        say(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if not all(results.values()):
        raise Stop("A lock check failed. Val's computer was NOT given the code. Tell Claude.")


def setup_val(url, val_token):
    parts = ["set -e", "umask 077", "mkdir -p /root/.hermes/skills/zingas/quo-texting /root/.hermes/skills/zingas/todo-list /usr/local/lib/zingas"]
    for src, dst in VAL_FILES.items():
        with open(os.path.join(HERE, src), "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        parts.append(f"echo '{b64}' | base64 -d > '{dst}'")
    parts += [
        "chmod 755 /usr/local/bin/zingas-quo",
        "chmod 644 /etc/supervisor/conf.d/zingas-quo-pickup.conf /usr/local/lib/zingas/zingas_todo.py",
        f"printf 'QUO_BRIDGE_URL=%s\\nVAL_DRAFT_TOKEN=%s\\n' '{url}' '{val_token}' > /root/.hermes/quo-bridge.env",
        "chmod 600 /root/.hermes/quo-bridge.env",
        "supervisorctl reread >/dev/null && supervisorctl update >/dev/null",
        "sleep 3",
        "supervisorctl status zingas-quo-pickup | awk '{print \"Val pickup program:\", $2}'",
        "zingas-quo check",
    ]
    r = subprocess.run([ORGO, "computers", "bash", COMPUTER], input="\n".join(parts) + "\n", text=True,
                       capture_output=True, timeout=300)
    out = (r.stdout or "").strip()
    say("\n".join(line for line in out.splitlines() if val_token not in line) or "(no answer from Val's computer)")
    if r.returncode != 0:
        raise Stop("Val's computer didn't finish the setup. Tell Claude.")


# ---------------------------------------------------------------- main

def main():
    lines = sys.stdin.read().splitlines()
    if len(lines) < 4 or not all(x.strip() for x in lines[:3]):
        raise Stop("Not everything was pasted. Nothing was changed.")
    quo_key, bot_token, vercel_token = (x.strip() for x in lines[:3])
    cell = us_phone(lines[3])
    if not cell:
        raise Stop("That cell number doesn't look like a US number. Nothing was changed.")

    quo_probe = QuoClient(quo_key, "")
    number_id = quo_number(quo_probe, cell)
    tg = TelegramClient(bot_token)
    gerrit_tg = approver_id(tg)
    vercel = Vercel(vercel_token)
    sb_url, sb_key = supabase()

    val_token = secrets.token_urlsafe(32)
    cron = secrets.token_urlsafe(32)
    tg_secret = secrets.token_urlsafe(32)
    vercel.project()
    vercel.set_env({"QUO_API_KEY": quo_key, "QUO_PHONE_NUMBER_ID": number_id, "APPROVALS_BOT_TOKEN": bot_token,
                    "APPROVALS_WEBHOOK_SECRET": tg_secret, "APPROVER_TELEGRAM_ID": str(gerrit_tg),
                    "VAL_DRAFT_TOKEN": val_token, "CRON_SECRET": cron, "GERRIT_CELL": cell,
                    "SUPABASE_URL": sb_url, "SUPABASE_SERVICE_KEY": sb_key, "AUTO_SEND_ENABLED": "false",
                    "QUO_WEBHOOK_SECRET": "not-set-yet"})
    say("Keys saved in Vercel's locked settings. Putting quo-bridge online (about 1 minute)...")
    url = vercel.deploy()
    say(f"quo-bridge is online at {url}")

    hook_url = url + "/api/quo"
    quo = QuoClient(quo_key, number_id)
    for w in quo.list_webhooks():
        if w.get("url") == hook_url or w.get("label") in ("zingas-bridge", "zingas-bridge-calls"):
            quo.delete_webhook(w["id"])
    hook = quo.create_webhook(hook_url, number_id)
    if not hook.get("key"):
        raise Stop("Quo made the alert but didn't give its signing key. Tell Claude.")
    keys = [hook["key"]]
    # Calls and voicemails, for Val's to-do list. Its own alert, so a refusal here
    # never stops texting from working.
    try:
        calls = quo.create_webhook(hook_url, number_id, events=CALL_EVENTS, label="zingas-bridge-calls")
        if calls.get("key"):
            keys.append(calls["key"])
        say("Quo's call and voicemail alert is connected.")
    except QuoError as e:
        say(f"Quo didn't connect the call and voicemail alert ({e}). Texts still work. Tell Claude.")
    vercel.set_env({"QUO_WEBHOOK_SECRET": ",".join(keys)})
    say("Quo's new-text alert is connected. Restarting quo-bridge with its key...")
    url = vercel.deploy()

    tg.call("setWebhook", {"url": url + "/api/telegram", "secret_token": tg_secret,
                           "allowed_updates": ["message", "callback_query"], "drop_pending_updates": True})
    say("Val Approvals bot is connected.")

    say("Checking the locks from outside:")
    check_locks(url, val_token, cron)

    say("Setting up Val's computer (her code and pickup program only)...")
    setup_val(url, val_token)
    try:
        tg.send(gerrit_tg, "Val Approvals is connected. Customer text drafts will show up here "
                           "with Approve, Edit and Skip. Nothing sends without your tap.")
    except TelegramError:
        pass
    say("\nDone. Next: delete the Vercel and Supabase tokens you made for this (they're not needed again).")


if __name__ == "__main__":
    try:
        main()
    except Stop as e:
        say(f"\nStopped: {e}")
        sys.exit(1)
