#!/usr/bin/env python3
# Runs ON Val's computer. Backs up, then layers Zinga's files onto the Orgo Hermes template.
import os, shutil, time, yaml

H = "/root/.hermes"
SRC = "/tmp/zingas-install"
stamp = time.strftime("%Y%m%d-%H%M%S")
bk = f"{H}/backups/pre-zingas-{stamp}"
os.makedirs(bk, exist_ok=True)
os.chmod(bk, 0o700)
for f in ("SOUL.md", "config.yaml", ".env"):
    if os.path.exists(f"{H}/{f}"):
        shutil.copy2(f"{H}/{f}", f"{bk}/{f}")
print("backup:", bk, sorted(os.listdir(bk)))

shutil.copy2(f"{SRC}/SOUL.md", f"{H}/SOUL.md")
dst = f"{H}/skills/zingas"
if os.path.exists(dst):
    shutil.rmtree(dst)
shutil.copytree(f"{SRC}/skills/zingas", dst)
print("skills:", sorted(os.listdir(dst)))

ours = yaml.safe_load(open(f"{SRC}/config.yaml"))
cfg = yaml.safe_load(open(f"{H}/config.yaml"))
for k in ("approvals", "hooks_auto_accept", "secrets", "session_reset"):
    cfg[k] = ours[k]
pt = cfg.setdefault("platform_toolsets", {})
pt["cli"] = ours["platform_toolsets"]["cli"]
pt["telegram"] = ours["platform_toolsets"]["telegram"]
mcp = cfg.setdefault("mcp_servers", {})
for name in ("mail-bridge", "obsidian-vault"):
    mcp[name] = ours["mcp_servers"][name]
tmp = f"{H}/config.yaml.tmp"
with open(tmp, "w") as fh:
    yaml.safe_dump(cfg, fh, default_flow_style=False, sort_keys=False, allow_unicode=True, width=1000)
os.replace(tmp, f"{H}/config.yaml")
print("config merged:", ["approvals", "hooks_auto_accept", "secrets", "session_reset", "platform_toolsets.cli/telegram", "mcp mail-bridge(off) + obsidian-vault"])

env = open(f"{H}/.env").read()
add = []
for line in ("OBSIDIAN_VAULT_PATH=/root/Documents/ZingasVault",
             "WIKI_PATH=/root/Documents/ZingasVault",
             "ASSISTANT_TIME_ZONE=America/Indiana/Indianapolis"):
    if not any(l.startswith(line.split("=")[0] + "=") for l in env.splitlines()):
        add.append(line)
if add:
    with open(f"{H}/.env", "a") as fh:
        fh.write("\n# Zinga's Assistant\n" + "\n".join(add) + "\n")
print("env lines added:", [a.split("=")[0] for a in add])

os.makedirs("/root/Documents/ZingasVault", exist_ok=True)
shutil.copy2(f"{SRC}/op-enable.py", "/usr/local/bin/zingas-assistant-op-enable")
os.chmod("/usr/local/bin/zingas-assistant-op-enable", 0o755)
print("vault dir and op-enable helper in place")

if os.path.exists(f"{SRC}/heartbeat.sh"):
    shutil.copy2(f"{SRC}/heartbeat.sh", "/usr/local/bin/zingas-assistant-heartbeat")
    os.chmod("/usr/local/bin/zingas-assistant-heartbeat", 0o755)
    shutil.copy2(f"{SRC}/heartbeat.supervisor.conf", "/etc/supervisor/conf.d/zingas-heartbeat.conf")
    print("heartbeat installed (run: supervisorctl reread && supervisorctl update)")

if os.path.exists(f"{SRC}/zingas_backup.py"):
    os.makedirs("/usr/local/lib/zingas", exist_ok=True)
    shutil.copy2(f"{SRC}/zingas_backup.py", "/usr/local/lib/zingas/zingas_backup.py")
    shutil.copy2(f"{SRC}/zingas_backup.py", "/usr/local/bin/zingas-backup")
    os.chmod("/usr/local/bin/zingas-backup", 0o755)
    shutil.copy2(f"{SRC}/zingas-backup.supervisor.conf", "/etc/supervisor/conf.d/zingas-backup.conf")
    print("nightly backup installed (starts after: supervisorctl reread && supervisorctl update)")

if os.path.exists(f"{SRC}/zingas_money.py"):
    os.makedirs("/usr/local/lib/zingas", exist_ok=True)
    for name in ("zingas_money.py", "money_prices.json"):
        shutil.copy2(f"{SRC}/{name}", f"/usr/local/lib/zingas/{name}")
    shutil.copy2(f"{SRC}/zingas_money.py", "/usr/local/bin/zingas-money")
    os.chmod("/usr/local/bin/zingas-money", 0o755)
    shutil.copy2(f"{SRC}/zingas-money.supervisor.conf", "/etc/supervisor/conf.d/zingas-money.conf")
    print("hourly cost count installed (starts after: supervisorctl reread && supervisorctl update)")

if os.path.exists(f"{SRC}/zingas_followups.py"):
    os.makedirs("/usr/local/lib/zingas", exist_ok=True)
    for name in ("zingas_todo.py", "zingas_inbox.py", "followup_wording.py", "zingas_followups.py"):
        shutil.copy2(f"{SRC}/{name}", f"/usr/local/lib/zingas/{name}")
    shutil.copy2(f"{SRC}/zingas_followups.py", "/usr/local/bin/zingas-followups")
    os.chmod("/usr/local/bin/zingas-followups", 0o755)
    shutil.copy2(f"{SRC}/zingas-followups.supervisor.conf", "/etc/supervisor/conf.d/zingas-followups.conf")
    print("quote follow-ups installed; they only make lists until f0-setup.sh turns them on "
          "(starts after: supervisorctl reread && supervisorctl update)")

if os.path.exists(f"{SRC}/quo_pickup.py"):
    shutil.copy2(f"{SRC}/quo_pickup.py", "/usr/local/bin/zingas-quo")
    os.chmod("/usr/local/bin/zingas-quo", 0o755)
    shutil.copy2(f"{SRC}/quo-pickup.supervisor.conf", "/etc/supervisor/conf.d/zingas-quo-pickup.conf")
    print("quo pickup installed (starts after: supervisorctl reread && supervisorctl update)")
