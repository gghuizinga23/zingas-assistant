#!/bin/bash
# ==========================================================================
# Zinga's Assistant: Val's check-in with healthchecks.io, every 10 minutes
# ==========================================================================
# Runs on Val's Orgo computer under supervisord (files/heartbeat.supervisor.conf).
# If the gateway is running it pings healthchecks.io; if not, it reports a
# failure so Gerrit is warned right away. It also reports a failure while the
# Plaud sign-in is broken (zingas-plaud leaves a flag file). If this computer is down, no ping
# arrives at all and healthchecks.io warns Gerrit by itself. The ping link
# lives in 1Password (HEALTHCHECKS_PING_URL) and is never written to a log.
set -u

OP_ENV=/root/.hermes/.op.env
REF="op://Zingas Assistant/Assistant Secrets/HEALTHCHECKS_PING_URL"
EVERY=600
PLAUD_BROKEN=/root/.hermes/plaud-login-broken

read_url() {
  [ -f "$OP_ENV" ] || return 1
  OP_SERVICE_ACCOUNT_TOKEN="$(sed -n 's/^OP_SERVICE_ACCOUNT_TOKEN=//p' "$OP_ENV")" \
    op read "$REF" 2>/dev/null
}

URL=""
while true; do
  [ -n "$URL" ] || URL="$(read_url || true)"
  if [ -z "$URL" ]; then
    echo "$(date -Is) no ping link from 1Password yet; trying again in 60s"
    sleep 60
    continue
  fi
  if [ -f "$PLAUD_BROKEN" ]; then
    # zingas-plaud made this file: the Plaud sign-in worked once and has stopped (plaud exit code 2).
    # A failed check makes healthchecks.io warn Gerrit; the message says what is wrong.
    curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "Plaud sign-in stopped. Do Plaud step P2 again." \
      "$URL/fail" && echo "$(date -Is) plaud sign-in stopped: reported"
  elif supervisorctl status hermes-gateway 2>/dev/null | grep -q RUNNING; then
    curl -fsS -m 10 --retry 3 -o /dev/null "$URL" && echo "$(date -Is) ok" || echo "$(date -Is) ping failed"
  else
    curl -fsS -m 10 --retry 3 -o /dev/null "$URL/fail" && echo "$(date -Is) gateway not running: reported"
  fi
  sleep "$EVERY"
done
