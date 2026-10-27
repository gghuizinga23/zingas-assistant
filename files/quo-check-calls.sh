#!/bin/bash
# ==========================================================================
# Zinga's Assistant: what did Quo do with the last calls? (read-only)
# ==========================================================================
# Run on Gerrit's laptop. Paste the Quo key into the hidden prompt (1Password: Zingas Bridge > Bridge Secrets >
# QUO_API_KEY). It is never shown and never saved. Only reads: quo-bridge's Quo alerts, what Quo sent quo-bridge
# about the newest calls and how quo-bridge answered, and the newest calls. Nothing changes; nobody gets a text.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

echo >&2
echo "Paste the Quo key (1Password: Zingas Bridge > Bridge Secrets > QUO_API_KEY), then press Return. Nothing shows while you paste." >&2
printf '> ' >&2
IFS= read -rs KEY
echo >&2
KEY="$(printf '%s' "$KEY" | tr -d '[:space:]')"
[ -n "$KEY" ] || { echo "Nothing pasted. Nothing was read." >&2; exit 1; }

printf '%s\n' "$KEY" | python3 -I "$HERE/quo_check_calls.py"
unset KEY
echo
echo "You can close this tab."
