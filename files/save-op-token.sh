#!/bin/bash
# ==========================================================================
# Zinga's Assistant: save Val's 1Password service-account token on her Orgo computer
# ==========================================================================
# Run on Gerrit's laptop. The token is typed into a hidden prompt, goes straight
# to Val's computer through the Orgo helper, and lands in ~/.hermes/.op.env
# (readable by root only). It is never shown on screen, never saved on this
# laptop, and never goes in a chat.
#
# Afterwards it checks, without showing any values:
#   - which vaults the token can open (must be "Zingas Assistant" only)
#   - which field names are in the "Assistant Secrets" note
set -euo pipefail

ORGO="${ORGO:-$HOME/.orgo-cli/bin/orgo}"
COMPUTER="${COMPUTER:-Hermes Agent}"

echo
echo "Paste Val's 1Password code (it starts with ops_), then press Return."
echo "Nothing shows while you paste. That is normal."
printf '> '
IFS= read -rs TOKEN
echo
TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
case "$TOKEN" in
  ops_*) ;;
  *) echo "That doesn't start with ops_. Nothing was saved. Copy the code again and re-run."; exit 1 ;;
esac

B64="$(printf 'OP_SERVICE_ACCOUNT_TOKEN=%s\n' "$TOKEN" | base64 | tr -d '\n')"
unset TOKEN

# The command goes over stdin, so the token never appears in this laptop's process list.
"$ORGO" computers bash "$COMPUTER" <<REMOTE
umask 077
echo '$B64' | base64 -d > /root/.hermes/.op.env
chmod 600 /root/.hermes/.op.env
python3 - <<'PY'
import json, os, subprocess
tok = open("/root/.hermes/.op.env").read().split("=", 1)[1].strip()
env = dict(os.environ, OP_SERVICE_ACCOUNT_TOKEN=tok)
def op(*a):
    r = subprocess.run(["op", *a, "--format", "json"], env=env, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        if a[0] == "vault":
            os.remove("/root/.hermes/.op.env")  # a code 1Password rejects is not kept
        raise SystemExit("1Password said no: " + r.stderr.strip().splitlines()[-1][:200])
    return json.loads(r.stdout or "null")
vaults = sorted(v["name"] for v in op("vault", "list"))
print("Saved on Val's computer.")
print("Vaults this code can open:", ", ".join(vaults) or "(none)")
if vaults != ["Zingas Assistant"]:
    print("PROBLEM: it must open only 'Zingas Assistant'.")
try:
    item = op("item", "get", "Assistant Secrets", "--vault", "Zingas Assistant")
    names = sorted(f.get("label", "") for f in item.get("fields", []) if f.get("label") and f.get("label") not in ("notesPlain",))
    print("Field names in Assistant Secrets:", ", ".join(names) or "(none yet, that's fine)")
except SystemExit as e:
    print(e)
PY
REMOTE
unset B64
echo
echo "Done. You can close this tab."
