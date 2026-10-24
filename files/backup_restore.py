#!/usr/bin/env python3
"""Runs on Gerrit's laptop (called by files/backup-restore.sh). Plain code.

Reads 3 lines on stdin (restore key id, restore key, backup password) and runs
the restore ON an Orgo computer: it sends files/zingas_backup.py there, pulls
the newest backup from Backblaze B2, unlocks it and unpacks it.

  test (default)  unpack into a scratch folder on Val's computer, compare every
                  file with the live one, then delete the scratch folder
  APPLY=1         put every file back in its place (for a rebuilt computer),
                  then restart Val's programs

Nothing is saved on this laptop. The keys go to the Orgo computer only for this
one run, inside the command's input (never on a command line), and are never printed.
"""

import base64
import os
import secrets
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ORGO = sys.argv[1] if len(sys.argv) > 1 else "orgo"
COMPUTER = sys.argv[2] if len(sys.argv) > 2 else "Hermes Agent"
APPLY = os.environ.get("APPLY") == "1"


def main() -> int:
    lines = [l.strip() for l in sys.stdin.read().splitlines()]
    if len(lines) < 3 or not all(lines[:3]):
        print("Need the key id, the key and the backup password. Nothing was changed.")
        return 2
    keys = lines[:4]
    for k in keys:
        if "ZBKEYS" in k or "\n" in k:
            print("That doesn't look right. Nothing was changed.")
            return 2
    with open(os.path.join(HERE, "zingas_backup.py"), "rb") as fh:
        prog = base64.b64encode(fh.read()).decode()
    tag = secrets.token_hex(4)
    script, folder = f"/tmp/zb-{tag}.py", f"/root/restore-test-{tag}"
    mode = "--apply" if APPLY else ""
    remote = f"""umask 077
echo '{prog}' | base64 -d > {script}
command -v gpg >/dev/null || {{ apt-get update -qq >/dev/null && apt-get install -y -qq gnupg >/dev/null; }}
python3 {script} restore --to {folder} --compare {mode} <<'ZBKEYS'
{chr(10).join(keys)}
ZBKEYS
rc=$?
rm -f {script}
"""
    if APPLY:
        remote += ("[ $rc -eq 0 ] && { supervisorctl reread >/dev/null; supervisorctl update >/dev/null; "
                   "supervisorctl restart all >/dev/null; supervisorctl status; }\n"
                   f"echo 'Unpacked copy kept in {folder} (delete it once Val works).'\n")
    else:
        remote += f"rm -rf {folder}\necho 'Test folder deleted.'\n"
    remote += "exit $rc\n"
    r = subprocess.run([ORGO, "computers", "bash", COMPUTER], input=remote, text=True,
                       capture_output=True, timeout=900)
    out = "\n".join(l for l in (r.stdout or "").splitlines() if not any(k and k in l for k in keys))
    print(out.strip() or (r.stderr or "").strip()[-500:] or "(no answer from the computer)")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
