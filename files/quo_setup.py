"""Zinga's Assistant: Quo part Q5. Puts quo-bridge online and connects everything.

Run by files/quo-setup.sh on Gerrit's laptop. Four keys arrive on stdin (never
argv, never saved, never printed), then Gerrit's cell number:
  1. QUO_API_KEY            (1Password: Zingas Bridge > Bridge Secrets)
  2. APPROVALS_BOT_TOKEN    (same note)
  3. a Vercel token         (made for this run; delete it after)
  4. a Supabase token       (made for this run; delete it after)
  5. Gerrit's cell          (for the 10-minute "a text is waiting" alert)

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
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE_DIR = os.path.join(HERE, "..", "quo-bridge")
sys.path.insert(0, BRIDGE_DIR)
from clients import QuoClient, QuoError, TelegramClient, TelegramError  # noqa: E402

ORGO = sys.argv[1] if len(sys.argv) > 1 else "orgo"
COMPUTER = sys.argv[2] if len(sys.argv) > 2 else "Hermes Agent"
NAME = "zingas-quo-bridge"
DEPLOY_FILES = ("app.py", "bridge.py", "clients.py", "store.py", "send_gate.py", "pyproject.toml", "vercel.json")
VAL_FILES = {   # laptop file -> place on Val's computer
    "quo_pickup.py": "/usr/local/bin/zingas-quo",
    "quo-pickup.supervisor.conf": "/etc/supervisor/conf.d/zingas-quo-pickup.conf",
    "skills/zingas/quo-texting/SKILL.md": "/root/.hermes/skills/zingas/quo-texting/SKILL.md",
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

def quo_number(quo):
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

def supabase(token):
    api = "https://api.supabase.com/v1"
    hdr = {"Authorization": "Bearer " + token}
    st, projects = http("GET", api + "/projects", headers=hdr)
    if st != 200:
        raise Stop(f"Supabase didn't accept the token (HTTP {st}).")
    proj = next((p for p in projects if p.get("name") == NAME), None)
    if not proj:
        st, orgs = http("GET", api + "/organizations", headers=hdr)
        if st != 200 or not orgs:
            raise Stop("Supabase shows no organization on this account.")
        org = orgs[0]
        if len(orgs) > 1:
            for i, o in enumerate(orgs, 1):
                say(f"  {i}. {o.get('name')}")
            org = orgs[int(ask("Which Supabase organization? Type its number: ")) - 1]
        say(f"Making a free Supabase project {NAME} (takes about 2 minutes)...")
        st, proj = http("POST", api + "/projects", {
            "name": NAME, "organization_slug": org["slug"], "db_pass": secrets.token_urlsafe(24),
            "region_selection": {"type": "specific", "code": "us-east-2"}}, headers=hdr)
        if st not in (200, 201):
            msg = proj.get("message") or proj.get("raw") or ""
            raise Stop(f"Supabase couldn't make the project (HTTP {st}): {msg}\n"
                       "The free plan allows 2 active projects. If that's the problem, tell Claude.")
    ref = proj["ref"]
    for _ in range(80):
        st, p = http("GET", f"{api}/projects/{ref}", headers=hdr)
        if p.get("status") == "ACTIVE_HEALTHY":
            break
        time.sleep(6)
    else:
        raise Stop("The Supabase project didn't finish starting. Run this again in a few minutes.")
    with open(os.path.join(BRIDGE_DIR, "schema.sql")) as fh:
        schema = fh.read()
    st, out = http("POST", f"{api}/projects/{ref}/database/query", {"query": schema}, headers=hdr, timeout=120)
    if st not in (200, 201):
        raise Stop(f"Couldn't make the tables (HTTP {st}).")
    st, keys = http("GET", f"{api}/projects/{ref}/api-keys?reveal=true", headers=hdr)
    key = next((k["api_key"] for k in keys if k.get("type") == "secret" and k.get("api_key")), None) \
        or next((k["api_key"] for k in keys if k.get("name") == "service_role" and k.get("api_key")), None)
    if not key:
        raise Stop("Couldn't read the Supabase server key.")
    say(f"Supabase project ready, tables made: messages, drafts, contacts, auto_send_stats, events")
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
    parts = ["set -e", "umask 077", "mkdir -p /root/.hermes/skills/zingas/quo-texting"]
    for src, dst in VAL_FILES.items():
        with open(os.path.join(HERE, src), "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        parts.append(f"echo '{b64}' | base64 -d > '{dst}'")
    parts += [
        "chmod 755 /usr/local/bin/zingas-quo",
        "chmod 644 /etc/supervisor/conf.d/zingas-quo-pickup.conf",
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
    if len(lines) < 5 or not all(x.strip() for x in lines[:4]):
        raise Stop("Not everything was pasted. Nothing was changed.")
    quo_key, bot_token, vercel_token, supabase_token = (x.strip() for x in lines[:4])
    cell = us_phone(lines[4])
    if not cell:
        raise Stop("That cell number doesn't look like a US number. Nothing was changed.")

    quo_probe = QuoClient(quo_key, "")
    number_id = quo_number(quo_probe)
    tg = TelegramClient(bot_token)
    gerrit_tg = approver_id(tg)
    vercel = Vercel(vercel_token)
    sb_url, sb_key = supabase(supabase_token)

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
        if w.get("url") == hook_url or w.get("label") == "zingas-bridge":
            quo.delete_webhook(w["id"])
    hook = quo.create_webhook(hook_url, number_id)
    if not hook.get("key"):
        raise Stop("Quo made the alert but didn't give its signing key. Tell Claude.")
    vercel.set_env({"QUO_WEBHOOK_SECRET": hook["key"]})
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
