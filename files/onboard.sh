#!/bin/bash
# ==========================================================================
# Zinga's Assistant — first-boot onboarding (from Nick's Stack, MIT)
# ==========================================================================
# Walks a new user through the steps that need a human:
#   1. Nous model auth   (device-code — required for the agent to think)
#   2. Telegram bot      (scan a QR — the signature onboarding)
#   3. 1Password vault   (optional — one service-account token unlocks the
#                         whole key map in config.yaml's secrets block)
#   4. next steps: Composio (Gmail + Calendar), quo-bridge, healthchecks
#
# Launched by an XFCE autostart entry inside a terminal. Idempotent: each
# step is skipped once satisfied, so re-running only does what's left.
set +e
export HOME=/root
export HERMES_HOME=/root/.hermes
export DISPLAY="${DISPLAY:-:99}"
export PATH=/usr/local/bin:/root/.local/bin:/root/.hermes/bin:/usr/bin:/bin:$PATH

VENV_PY=/usr/local/lib/hermes-agent/venv/bin/python
ENV_FILE="$HERMES_HOME/.env"
OP_ENV="$HERMES_HOME/.op.env"
STAMP=/var/lib/orgo/zingas-assistant-onboarded
mkdir -p /var/lib/orgo "$HERMES_HOME"

hr() { printf '\n\033[1;36m%s\033[0m\n' "────────────────────────────────────────────────────────"; }
say() { printf '\033[1;32m%s\033[0m\n' "$*"; }

clear 2>/dev/null
say "  Welcome to Zinga's Assistant — setup"
hr

# --- 1. Nous model auth ----------------------------------------------------
if [ ! -s "$HERMES_HOME/auth.json" ]; then
  say "Step 1/4 — Connect your Nous account (model: gpt-5.5)"
  echo "A device-code sign-in will open. Follow the URL + code it prints."
  echo "Use your Nous Portal account (pay-as-you-go credits). Do NOT connect a"
  echo "ChatGPT sign-in: an always-on agent on a consumer login breaks its terms."
  echo
  hermes auth add nous --type oauth
  echo
  if [ -s "$HERMES_HOME/auth.json" ]; then
    # 1-token sanity call: a zero-credit Nous account 404s on every model
    # call while everything looks green — fail loudly here, not silently.
    echo "Verifying the model can think (1-token test call)…"
    if hermes -z "Reply with exactly: ok" >/tmp/zingas-assistant-modelcheck 2>&1 \
       && grep -qi "ok" /tmp/zingas-assistant-modelcheck; then
      say "Model check passed ✓"
    else
      printf '\033[1;31m%s\033[0m\n' "Model test call FAILED — most often a Nous account with zero credits."
      echo "Add credits at portal.nousresearch.com, then re-run this setup."
    fi
  fi
else
  say "Step 1/4 — Model account already connected ✓"
fi

# --- 2. Telegram bot via QR ------------------------------------------------
if ! grep -q '^TELEGRAM_BOT_TOKEN=..' "$ENV_FILE" 2>/dev/null; then
  hr
  say "Step 2/4 — Create your Telegram bot (scan the QR)"
  echo "A QR code opens in Chrome. Scan it with your phone, then tap"
  echo "'Create Bot' in Telegram. Your bot + allowlist are set automatically."
  echo
  "$VENV_PY" /usr/local/bin/zingas-assistant-telegram-pair.py
  if grep -q '^TELEGRAM_BOT_TOKEN=..' "$ENV_FILE" 2>/dev/null; then
    say "Telegram connected — restarting the gateway to enable it…"
    supervisorctl restart hermes-gateway 2>/dev/null || \
      { [ -f "$HERMES_HOME/gateway.pid" ] && kill -USR1 "$(cat "$HERMES_HOME/gateway.pid")" 2>/dev/null; }
  fi
else
  say "Step 2/4 — Telegram bot already connected ✓"
fi

# --- 3. 1Password (optional, but it IS the stack's secret plane) -----------
hr
if [ -s "$OP_ENV" ]; then
  say "Step 3/4 — 1Password already connected ✓"
else
  say "Step 3/4 — Connect 1Password (optional, recommended)"
  cat <<'OPINTRO'
  One service-account token unlocks every key this stack knows about:
  config.yaml maps the env vars to op://Zingas Assistant/Assistant Secrets/<FIELD>.
  Setup (once, on 1password.com): vault "Zingas Assistant" -> Secure Note
  "Assistant Secrets" -> fields named exactly like the env vars (see the
  key contract in ~/.hermes/.env) -> a service account that can read only
  vault "Zingas Assistant". Never give it "Zingas Bridge": that vault is for
  quo-bridge alone.
OPINTRO
  printf '  Paste your service-account token (ops_…) or press Enter to skip: '
  read -r OPTOK
  if [ -n "$OPTOK" ]; then
    umask 077
    printf 'OP_SERVICE_ACCOUNT_TOKEN=%s\n' "$OPTOK" > "$OP_ENV"
    unset OPTOK
    python3 /usr/local/bin/zingas-assistant-op-enable || true
    echo "Checking…"
    hermes secrets onepassword status || true
    supervisorctl restart hermes-gateway 2>/dev/null || true
    say "1Password wired — keys resolve at every hermes start."
  else
    echo "Skipped. Re-run this setup any time, or: echo 'OP_SERVICE_ACCOUNT_TOKEN=ops_…' > ~/.hermes/.op.env"
  fi
fi

# --- 4. The rest of the setup ------------------------------------------------
hr
say "Step 4/4 — The rest of your setup"
cat <<'NEXT'
  • Composio (Gmail + Calendar): COMPOSIO_CONSUMER_KEY in 1Password. Allow only
      read mail, search mail, create draft, read calendar. Never "send email".
  • quo-bridge (customer texts): its keys go in its OWN env file, never in
      ~/.hermes/.env, so the agent cannot text a customer by itself.
  • healthchecks.io: HEALTHCHECKS_PING_URL in 1Password. A missed ping texts
      Gerrit's cell.
NEXT
hr

# Stamp only when the two required steps are done, so we stop auto-launching.
if [ -s "$HERMES_HOME/auth.json" ] && grep -q '^TELEGRAM_BOT_TOKEN=..' "$ENV_FILE" 2>/dev/null; then
  date -Iseconds > "$STAMP"
  say "Setup complete. This window won't reappear. Talk to your assistant on Telegram."
else
  say "Setup paused — re-run this setup from the desktop to finish."
fi
echo
read -r -p "Press Enter to close…" _
