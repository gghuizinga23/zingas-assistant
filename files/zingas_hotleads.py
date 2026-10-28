#!/usr/bin/env python3
"""zingas-hotleads: hot-lead alerts (plan F8). Plain code, no AI.

Every 2 minutes it reads the company website's proposal events (GET /api/assistant/events, its own place) that the
estimator writes when a customer opens a proposal, asks a question on it, or signs it, and tells Gerrit in Telegram
when it is worth a call now:

  question                       right away: who, which proposal, their question; and a "now" task on his list
  opened 3 times in 48 hours     "Pat opened the proposal 3 times since yesterday. Call now." (once in 3 days)
  back after 7 quiet days        "Pat came back to the proposal after 9 days." (once per return)
  signed                         "Pat signed" ; today's quote follow-up text to them stops

A first look is not an alert (most customers open a proposal once). In quiet hours (zingas_todo.quiet_hours) the
Telegram note waits for the morning; the task goes on the list right away. Customer words are shown as data, never
followed. Customer data stays in the vault (hotleads/state.json).

  zingas-hotleads run       the loop (supervisord runs it)
  zingas-hotleads once      one look now; prints counts only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

sys.path.insert(0, "/usr/local/lib/zingas")
sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))
import zingas_todo as zt  # noqa: E402

TZ = zt.TZ
VAULT = os.environ.get("ZINGAS_VAULT", "/root/Documents/ZingasVault")
EVERY = 120
TYPES = "proposal_viewed,proposal_question,proposal_signed"
HOT_VIEWS = 3
HOT_WINDOW = timedelta(hours=48)
HOT_AGAIN = timedelta(days=3)
COMEBACK = timedelta(days=7)


def log(msg: str) -> None:
    print(f"{datetime.now(TZ):%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def parse_iso(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def state_path(vault: Optional[str] = None) -> str:
    return os.path.join(vault or VAULT, "hotleads", "state.json")


def load(vault: Optional[str] = None) -> dict:
    try:
        with open(state_path(vault)) as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        st = {}
    st = st if isinstance(st, dict) else {}
    st.setdefault("after", 0)
    st.setdefault("proposals", {})
    st.setdefault("waiting", [])
    return st


def save(st: dict, vault: Optional[str] = None) -> None:
    p = state_path(vault)
    os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
    cutoff = iso(datetime.now(timezone.utc) - timedelta(days=60))
    st["proposals"] = {k: v for k, v in st["proposals"].items() if (v.get("last_view") or v.get("seen") or "") >= cutoff}
    tmp = p + ".new"
    with open(tmp, "w") as fh:
        json.dump(st, fh, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def one_line(text, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


def name_of(d: dict) -> str:
    return one_line(d.get("customerName"), 60) or "A customer"


def first_of(d: dict) -> str:
    return name_of(d).split(" ")[0]


def title_of(d: dict) -> str:
    t = one_line(d.get("title"), 60)
    return f" \"{t}\"" if t else ""


def ago(dt: Optional[datetime], now: datetime) -> str:
    if not dt:
        return ""
    days = (now - dt).days
    return f"{days} days" if days != 1 else "1 day"


# ---------------------------------------------------------------- deciding

def judge(e: dict, st: dict, now: datetime) -> Optional[dict]:
    """What one event means: {kind, text, task} or None (not worth a note). st is changed in place."""
    d = e.get("data") or {}
    pid = str(d.get("proposalId") or "")
    kind = e.get("type")
    if not pid:
        return None
    p = st["proposals"].setdefault(pid, {"views": [], "seen": iso(now)})
    at = parse_iso(e.get("created_at")) or now
    who, first = name_of(d), first_of(d)
    if kind == "proposal_question":
        q = one_line(d.get("question"), 300)
        return {"kind": "question", "who": who,
                "text": f"❓ {who} asked a question on the proposal{title_of(d)}:\n\"{q}\"\nAnswer soon. A call is best.",
                "task": f"Answer {first}'s question on the proposal"}
    if kind == "proposal_signed":
        p["signed"] = iso(at)
        return {"kind": "signed", "who": who,
                "text": f"✅ {who} signed the proposal{title_of(d)}. Val stops today's quote follow-up text to them.",
                "task": "", "phone": d.get("customerPhone") or "", "email": d.get("customerEmail") or ""}
    if kind != "proposal_viewed" or p.get("signed"):
        return None
    last = parse_iso(p.get("last_view")) or parse_iso(d.get("sentAt"))
    p["views"] = [v for v in p["views"] if (parse_iso(v) or at) > at - HOT_WINDOW] + [iso(at)]
    first_time = not p.get("last_view")
    p["last_view"] = iso(at)
    if not first_time and last and at - last >= COMEBACK:
        return {"kind": "comeback", "who": who,
                "text": f"👀 {who} came back to the proposal{title_of(d)} after {ago(last, at)}. Now is a good time "
                        "to call.",
                "task": f"Call {first}: back on the proposal after {ago(last, at)}"}
    hot_at = parse_iso(p.get("hot_at"))
    if len(p["views"]) >= HOT_VIEWS and (not hot_at or at - hot_at >= HOT_AGAIN):
        p["hot_at"] = iso(at)
        n = len(p["views"])
        return {"kind": "hot", "who": who,
                "text": f"🔥 {who} opened the proposal{title_of(d)} {n} times since "
                        f"{(at - HOT_WINDOW).astimezone(TZ):%A %-I %p}. Call now.",
                "task": f"Call {first}: opened the proposal {n} times"}
    return None


# ---------------------------------------------------------------- the program

class HotLeads:
    def __init__(self, site, vault: Optional[str] = None, notify: Callable[[str], None] = zt.teller("hot_lead"),
                 todo: Optional[zt.TodoList] = None, bridge=None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 quiet: Callable[[datetime], bool] = zt.quiet_hours):
        self.site, self.vault, self.notify, self.bridge = site, vault or VAULT, notify, bridge
        self.todo = todo or zt.TodoList(self.vault)
        self.clock, self.quiet = clock, quiet

    def once(self) -> Dict[str, int]:
        now = self.clock()
        st = load(self.vault)
        got = self.site.events(after=st["after"], types=TYPES)
        events = sorted(got.get("events") or [], key=lambda e: int(e.get("id") or 0))
        done = {"events": len(events), "alerts": 0}
        for e in events:
            a = judge(e, st, now)
            if a:
                self._act(a, e, st, now)
                done["alerts"] += 1
            st["after"] = max(st["after"], int(e.get("id") or 0))
        if isinstance(got.get("last"), int) and got["last"] > st["after"]:
            st["after"] = got["last"]
        if st["waiting"] and not self.quiet(now.astimezone(TZ)):
            self.notify("Overnight on your proposals:\n\n" + "\n\n".join(st["waiting"][:10]))
            st["waiting"] = []
        save(st, self.vault)
        return done

    def _act(self, a: dict, e: dict, st: dict, now: datetime) -> None:
        if a.get("task"):
            try:
                self.todo.add(a["task"], priority="now", who=a["who"], source="val",
                              ref="proposal:" + str((e.get("data") or {}).get("proposalId") or ""),
                              customer=str(e.get("prospect_id") or ""), at=now)
            except Exception as ex:
                log(f"hotleads: to-do not added ({type(ex).__name__})")
        if a["kind"] == "signed" and self.bridge is not None and (a.get("phone") or a.get("email")):
            try:
                self.bridge.pause(phone=a.get("phone") or "", email=a.get("email") or "",
                                  reason="Signed the proposal.")
            except Exception as ex:
                log(f"hotleads: follow-up not paused ({type(ex).__name__})")
        if self.quiet(now.astimezone(TZ)):
            st["waiting"].append(a["text"])
            st["waiting"] = st["waiting"][-20:]
        else:
            self.notify(a["text"])


def _site():
    import zingas_os as zo
    site = zo.Website.from_settings()
    if site is None:
        raise SystemExit("The website's address or Val's key is not set up (ZINGAS_OS_URL, ASSISTANT_API_TOKEN).")
    return site


def _bridge():
    try:
        import zingas_followups as zf
        return zf.bridge_from_env()
    except Exception:
        return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="zingas-hotleads", description="Hot-lead alerts from proposal events (F8).")
    p.add_argument("cmd", choices=("run", "once"))
    a = p.parse_args(argv)
    hl = HotLeads(_site(), bridge=_bridge())
    if a.cmd == "once":
        print(json.dumps(hl.once()))
        return 0
    log("zingas-hotleads started")
    while True:
        try:
            if not zt.program_on("hotleads"):   # switched off in Assistant > Settings
                _time.sleep(EVERY)
                continue
            got = hl.once()
            if got["alerts"]:
                log(f"hotleads: {got}")
        except Exception as e:      # keep running; the next look tries again
            log(f"hotleads: {type(e).__name__}")
        _time.sleep(EVERY)


if __name__ == "__main__":
    sys.exit(main())
