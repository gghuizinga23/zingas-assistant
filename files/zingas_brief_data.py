#!/usr/bin/env python3
"""Runs right before each morning and evening brief (hermes cron --script).
Its output goes into Val's brief prompt. Plain code, no AI.

It prints Gerrit's to-do list exactly as the brief must show it, with tasks
added since the last brief marked 🆕, then notes the time of this brief.
Installed at ~/.hermes/scripts/zingas_brief_data.py.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, "/usr/local/lib/zingas")
sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))
import zingas_todo as zt  # noqa: E402


def last_path(vault: str) -> str:
    return os.path.join(vault, "todo", "last-brief.txt")


def shown(since: str) -> str:
    try:
        return datetime.fromisoformat(since).astimezone(zt.TZ).strftime("%A %-I:%M %p")
    except ValueError:
        return "none yet"


def main(vault: str = zt.VAULT, now=None) -> str:
    now = now or zt.now_local()
    todo = zt.TodoList(vault)
    try:
        with open(last_path(vault)) as fh:
            since = fh.read().strip()
    except OSError:
        since = ""
    kind = "Morning" if now.hour < 12 else "Evening"
    out = [f"BRIEF: {kind}, {now:%A, %B %-d} ({now:%-I:%M %p} Indianapolis)",
           f"LAST BRIEF: {shown(since)}",
           "--- TO-DO LIST STARTS (copy the lines below into the brief exactly; never copy this line) ---",
           zt.render_brief(todo, since=since or None, today=now.date()),
           "--- TO-DO LIST ENDS (never copy this line) ---"]
    os.makedirs(os.path.dirname(last_path(vault)), mode=0o700, exist_ok=True)
    with open(last_path(vault), "w") as fh:
        fh.write(zt.stamp())
    return "\n".join(out)


if __name__ == "__main__":
    print(main())
