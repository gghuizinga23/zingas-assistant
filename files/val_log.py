"""Zinga's Assistant: show what Val did, from quo-bridge's events table. Read only.

Run by files/val-log.sh on Gerrit's laptop (the Supabase app there is already signed in):
    bash files/val-log.sh             today, Indianapolis time
    bash files/val-log.sh 3           the last 3 days
    bash files/val-log.sh 1 followups only lines whose program or kind has "followups" in it
It prints one line per event, oldest first: the time, where it came from, what happened.
Val's own lines are "val:<program>"; quo-bridge's are its own kinds ("followups", "sent", "watchdog" ...).
The hourly "cost_posted" rows are left out. Python standard library only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Indiana/Indianapolis")
ORG = "Zingas Assistant"
SUPABASE = shutil.which("supabase") or "/opt/homebrew/bin/supabase"
NOISE = ("cost_posted",)


def sb(*args, timeout=120):
    out = subprocess.run([SUPABASE, *args, "-o", "json"], capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise SystemExit("Supabase didn't answer: " + (out.stderr.strip().splitlines() or ["?"])[-1])
    text = out.stdout
    starts = [i for i in (text.find("["), text.find("{")) if i >= 0]
    return json.loads(text[min(starts):]) if starts else []


def project_ref() -> str:
    org = next((o for o in sb("orgs", "list") if o.get("name") == ORG), None)
    if not org:
        raise SystemExit(f"No Supabase organization named {ORG!r} on this laptop's Supabase sign-in.")
    proj = next((p for p in sb("projects", "list") if p.get("organization_id") == org["id"]), None)
    if not proj:
        raise SystemExit(f"No Supabase project in {ORG!r}.")
    return proj.get("ref") or proj["id"]


def main(argv) -> int:
    days = int(argv[0]) if argv and argv[0].isdigit() else 1
    match = (argv[1] if len(argv) > 1 else "").lower()
    if not re.fullmatch(r"[a-z0-9:-]*", match):
        raise SystemExit("The filter can only have letters, numbers, ':' and '-'.")
    start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    work = tempfile.mkdtemp(prefix="val-log-")
    try:
        subprocess.run([SUPABASE, "link", "--project-ref", project_ref(), "--workdir", work],
                       capture_output=True, text=True, timeout=120, check=True)
        noise = ",".join(f"'{n}'" for n in NOISE)
        where = f"at >= '{start.isoformat()}' and kind not in ({noise})"
        if match:
            where += f" and kind ilike '%{match}%'"
        got = sb("db", "query", "--linked", "--workdir", work,
                 "select to_char(at at time zone 'America/Indiana/Indianapolis', 'YYYY-MM-DD\"T\"HH24:MI:SS') as local, "
                 f"kind, detail from events where {where} order by at asc, id asc limit 5000", timeout=180)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    rows = got.get("rows", []) if isinstance(got, dict) else got
    if not rows:
        print(f"Nothing logged since {start:%a %b %-d}.")
        return 0
    day = None
    for r in rows:
        at = datetime.fromisoformat(str(r["local"]))
        if at.date() != day:
            day = at.date()
            print(f"\n== {at:%A %B %-d}")
        detail = " ".join(str(r.get("detail") or "").split())
        print(f"{at:%-I:%M:%S %p}  {r['kind']:<16} {detail[:220]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
