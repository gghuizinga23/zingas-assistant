#!/usr/bin/env python3
"""Price and competitor answers (plan F6). Plain code, no AI of its own.

When a customer brings up price or another company (Budget Blinds, Home Depot, Costco, "too expensive", "got a
cheaper quote"), Val's draft uses Gerrit's own answer for it, in his voice. Never a price, an amount, a discount
or a promise to beat a price, and never a bad word about the other company.

Gerrit's answers live in the vault (value-answers.md), never in git. Gerrit tells Val in Telegram, and Val saves
them with this program:

  zingas-answers show                          every saved answer
  zingas-answers set <topic> --text-file -     save Gerrit's answer for one topic (his words, as he said them)
  zingas-answers remove <topic>                take one out
  zingas-answers for --about "<what they said>"  the block a draft gets (what Val reads before an email draft)

Topics: price, budget_blinds, big_box (Home Depot, Lowe's, Menards), costco, online (Blinds.com, Amazon, Next Day
Blinds), other_quote (any other company or "a cheaper quote"), and general (Gerrit's main value points, used with
every one of them).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Optional

VAULT = os.environ.get("ZINGAS_VAULT", "/root/Documents/ZingasVault")
FILE = "value-answers.md"
MAX_ANSWER = 1200

TOPICS = {
    "price": "Price is the worry (too expensive, over budget, more than they thought)",
    "budget_blinds": "Budget Blinds",
    "big_box": "Home Depot, Lowe's or Menards",
    "costco": "Costco",
    "online": "Online stores (Blinds.com, Amazon, Next Day Blinds, SelectBlinds)",
    "other_quote": "Another company or a cheaper quote",
    "general": "Gerrit's main value points (used with every topic)",
}

# What makes a topic come up. Whole words, any case. "general" never comes up by itself.
PATTERNS = {
    "budget_blinds": r"budget\s*blinds?",
    "big_box": r"home\s*depot|lowe'?s|menards",
    "costco": r"costco",
    "online": r"blinds\.com|amazon|next\s*day\s*blinds|select\s*blinds|selectblinds|online",
    "other_quote": r"(other|another|second|cheaper|lower|better)\s+(quote|price|bid|estimate|company|guy)s?"
                   r"|quote\s+from|shopping\s+around|compar(e|ing)\s+(quotes|prices)|went\s+with\s+someone",
    "price": r"too\s+(expensive|much|high|pricey)|(over|out\s+of)\s+(our|my|the)\s+budget|pricey|expensive"
             r"|more\s+than\s+(we|i)\s+(thought|expected|wanted)|can'?t\s+afford|sticker\s+shock|price|cost",
}
_COMPILED = {k: re.compile(r"\b(?:" + v + r")\b", re.I) for k, v in PATTERNS.items()}


def path(vault: Optional[str] = None) -> str:
    return os.path.join(vault or VAULT, FILE)


def topics_in(*texts: str) -> List[str]:
    """The topics these words bring up, in TOPICS order. A named company also counts as other_quote's cousin,
    so only the named one is listed."""
    words = " ".join(t for t in texts if t)
    return [k for k in TOPICS if k in _COMPILED and _COMPILED[k].search(words)]


def load(vault: Optional[str] = None) -> Dict[str, str]:
    """{topic: Gerrit's answer}. The file is markdown: "## <topic>" then the answer. Unknown topics are kept
    (Gerrit may add his own); empty ones are left out."""
    try:
        with open(path(vault), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return {}
    out, topic, lines = {}, None, []
    for row in text.splitlines():
        m = re.match(r"^##\s+([a-z_]{1,32})\s*$", row.strip())
        if m:
            if topic and "\n".join(lines).strip():
                out[topic] = "\n".join(lines).strip()
            topic, lines = m.group(1), []
        elif topic and not row.startswith("<!--"):
            lines.append(row)
    if topic and "\n".join(lines).strip():
        out[topic] = "\n".join(lines).strip()
    return out


def save(answers: Dict[str, str], vault: Optional[str] = None) -> None:
    os.makedirs(vault or VAULT, mode=0o700, exist_ok=True)
    order = [k for k in TOPICS if k in answers] + sorted(k for k in answers if k not in TOPICS)
    body = ["# Gerrit's price and competitor answers (plan F6)",
            "<!-- Val uses these in drafts when a customer brings up price or another company. Gerrit's own "
            "words. Changed with zingas-answers; never a price or a discount. -->", ""]
    for k in order:
        body += [f"## {k}", answers[k].strip(), ""]
    tmp = path(vault) + ".new"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(body))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path(vault))


PRICE_IN_ANSWER = re.compile(r"\$\s*\d|\d+\s*(%|percent)|\b\d+\s*(dollars|bucks)\b", re.I)


def check_answer(text: str) -> Optional[str]:
    """Why an answer can't be saved, or None. Gerrit's words otherwise stay as he said them."""
    text = (text or "").strip()
    if not text:
        return "The answer is empty."
    if len(text) > MAX_ANSWER:
        return f"The answer is too long (at most {MAX_ANSWER} characters)."
    if PRICE_IN_ANSWER.search(text):
        return "The answer has a price, an amount or a percent. Drafts never carry those. Say it without the number."
    return None


def prompt_block(*texts: str, vault: Optional[str] = None) -> str:
    """What a draft gets when price or a competitor came up; "" when nothing did."""
    found = topics_in(*texts)
    if not found:
        return ""
    answers = load(vault)
    names = ", ".join(TOPICS[k].split(" (")[0] for k in found)
    rules = ("- Use Gerrit's answer below that fits, in his voice and short: one or two points, not all of them.\n"
             "- Never a price, an amount, a percent, a discount, financing numbers or a promise to match or beat "
             "a price.\n"
             "- Never say a bad word about the other company. Say what Zinga's does.\n"
             "- If they ask for a lower price or name a lower quote, write the reply and say in note_for_gerrit: "
             "\"Price came up. Call them.\" Gerrit decides on price himself.")
    have = [k for k in found + ["general"] if k in answers]
    if not have:
        return ("## Price or a competitor came up (" + names + ")\n" + rules + "\n"
                "- Gerrit's own answers are not saved yet. Do not argue value in detail: say Gerrit will go over "
                "it with them, and say in note_for_gerrit: \"Price or a competitor came up. Your answers for this "
                "are not saved yet.\"")
    blocks = "\n\n".join(f"<answer topic=\"{k}\">\n{answers[k]}\n</answer>" for k in dict.fromkeys(have))
    return ("## Price or a competitor came up (" + names + ")\n" + rules + "\n"
            "Gerrit's own answers (his words; use the ideas, keep it short):\n" + blocks)


# ---------------------------------------------------------------- the command

def _read_text(arg: str) -> str:
    return sys.stdin.read() if arg == "-" else open(arg, encoding="utf-8").read()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="zingas-answers", description="Gerrit's price and competitor answers (F6).")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    s = sub.add_parser("set")
    s.add_argument("topic")
    s.add_argument("--text-file", required=True, help="the answer, or - to read it from the input")
    r = sub.add_parser("remove")
    r.add_argument("topic")
    f = sub.add_parser("for")
    f.add_argument("--about", required=True)
    a = p.parse_args(argv)

    if a.cmd == "show":
        got = load()
        if not got:
            print("No answers saved yet. Topics: " + ", ".join(TOPICS))
            return 0
        for k, v in got.items():
            print(f"{k} ({TOPICS.get(k, 'Gerrit added this one')}):\n{v}\n")
        missing = [k for k in TOPICS if k not in got]
        if missing:
            print("Not saved yet: " + ", ".join(missing))
        return 0
    if a.cmd == "for":
        print(prompt_block(a.about) or "Price or a competitor did not come up.")
        return 0
    topic = a.topic.strip().lower().replace("-", "_").replace(" ", "_")
    if not re.fullmatch(r"[a-z_]{1,32}", topic):
        print("A topic is lowercase letters and _ (for example budget_blinds).")
        return 2
    got = load()
    if a.cmd == "remove":
        if topic not in got:
            print(f"No answer saved for {topic}.")
            return 1
        got.pop(topic)
        save(got)
        print(f"Removed the answer for {topic}.")
        return 0
    text = _read_text(a.text_file).strip()
    why = check_answer(text)
    if why:
        print(why)
        return 1
    old = got.get(topic)
    got[topic] = text
    save(got)
    stamp = datetime.now().strftime("%b %-d")
    print(f"Saved your answer for {TOPICS.get(topic, topic)}" + (" (it replaces the old one)" if old else "")
          + f", {stamp}. Val uses it in drafts from now on.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
