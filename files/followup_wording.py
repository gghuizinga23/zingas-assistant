"""F0: the fixed follow-up wordings, in Gerrit's voice (VOICE.md, 2026-10-21).

Only the first name, the product and the season change. No prices, discounts,
money words or em dashes, so later these can earn sending without the morning tap.
Each touch is a text (from the Quo number) and an email (a reply in the estimate's
thread, so the PDF is right there).

To change a wording, change it here; test_zingas_followups.py checks the rules.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Tuple

SIGN = "Thanks!\nGerrit"

# The touch points after day 7 rotate through these ideas, in this order.
ROTATION = ("question", "season", "idea", "help")
TOUCHES = ("48 hours", "7 days", "day 14", "day 21", "day 28", "day 42", "day 56", "day 70", "day 84", "day 90")


def season_line(today: date) -> str:
    m = today.month
    if m in (9, 10, 11):
        return ("With install lead times around 6 to 8 weeks, now is a great time to get things ordered "
                "if you'd like everything in before the holidays.")
    if m in (12, 1, 2):
        return "Hope you're staying warm! Winter is a great time to plan ahead so everything is in before spring."
    if m in (3, 4, 5):
        return "Spring gets busy for us, so I wanted to reach out before the install schedule fills up."
    return "Hope you're enjoying the summer!"


IDEAS = {
    "screen": "One thing I forgot to mention: motorized screens are a game changer for keeping the bugs and the "
              "afternoon sun out, and they go up and down with one tap on your phone.",
    "pergola": "One thing I forgot to mention: we can add lighting, screens or a motor to the louvers, so you can "
               "use the space well into the evening.",
    "awning": "One thing I forgot to mention: we can add a motor and a wind sensor to the awning, so it closes by "
              "itself when the weather turns.",
    "shutter": "One thing I forgot to mention: our shutters are custom made for each window, and the warranty is "
               "one of the best out there.",
    "": "One thing I forgot to mention: we can add motorization to most of what we talked about, so everything "
        "opens and closes from your phone or on a schedule.",
}


def idea_line(product: str) -> str:
    p = product.lower()
    for key, line in IDEAS.items():
        if key and key in p:
            return line
    return IDEAS[""]


def kind_of(touch: str) -> str:
    """'48 hours', '7 days', 'close', or one of ROTATION for the touch points."""
    if touch in ("48 hours", "7 days"):
        return touch
    if touch == "day 90":
        return "close"
    if touch in TOUCHES:
        return ROTATION[(TOUCHES.index(touch) - 2) % len(ROTATION)]
    return "question"


def write(touch: str, first: str, product: str, today: date) -> Dict[str, str]:
    """Returns {"text", "email_subject", "email_body"} for one fixed touch."""
    hey = f"Hey {first}!" if first else "Hey there!"
    hi = f"Hi {first}," if first else "Hi there,"
    est = f"the {product} estimate" if product else "the estimate"
    it = f"the {product}" if product else "your project"
    k = kind_of(touch)
    if k == "48 hours":
        text = (f"{hey} This is Gerrit Huizinga with Zinga's.\n\n"
                f"Just wanted to follow up and see if you had a chance to look over {est} I sent over. "
                f"Any questions, or would you like to move forward?\n\n{SIGN}")
        body = (f"{hi}\n\nI hope you're doing well! I wanted to follow up on {est} I sent over after our visit. "
                f"It's attached to the email below in case you need it again.\n\n"
                f"Please let me know if you have any questions or if there's anything I can clarify. "
                f"If you're ready to move forward, I'd be happy to help with the next steps.\n\n{SIGN}")
    elif k == "7 days":
        text = (f"{hey} Hope you're having a good week.\n\n"
                f"Just checking in on {est}. Let me know if any questions came up or if you'd like me to "
                f"walk you through anything again.\n\n{SIGN}")
        body = (f"{hi}\n\nJust checking in on {est} from last week. If any questions came up, I'm happy to "
                f"help, whether that's a quick call or a reply here.\n\n"
                f"Let me know how else I can help!\n\n{SIGN}")
    elif k == "question":
        text = (f"{hey} Gerrit with Zinga's here.\n\nQuick question: is there anything I can help clear up "
                f"on {it}? Happy to help however I can.\n\n{SIGN}")
        body = (f"{hi}\n\nI wanted to check in and see if there's anything I can help clear up on {est}. "
                f"If you're comparing options, I'm happy to walk through warranty, who installs and what's "
                f"custom so it's an easy apples-to-apples look.\n\n{SIGN}")
    elif k == "season":
        line = season_line(today)
        text = f"{hey} Gerrit with Zinga's.\n\n{line} Is {it} still on your list?\n\n{SIGN}"
        body = (f"{hi}\n\n{line}\n\nI wanted to see if {it} is still on your list. Let me know if you have "
                f"any questions or if you'd like to move forward.\n\n{SIGN}")
    elif k == "idea":
        line = idea_line(product)
        text = f"{hey} Gerrit with Zinga's.\n\n{line} Happy to show you if you're curious!\n\n{SIGN}"
        body = f"{hi}\n\n{line}\n\nHappy to show you if you're curious. Just reply here or give me a call.\n\n{SIGN}"
    elif k == "help":
        text = (f"{hey} Gerrit with Zinga's.\n\nIf it would help, I'm happy to hop on a quick call or stop "
                f"back out so everyone can see the samples in person. Just let me know what works best for "
                f"you!\n\n{SIGN}")
        body = (f"{hi}\n\nIf it would help, I'd be happy to hop on a quick call or stop back out so everyone "
                f"who's part of the decision can see the samples in person.\n\n"
                f"Just let me know what works best for you!\n\n{SIGN}")
    else:   # close: day 90
        text = (f"{hey} This is Gerrit with Zinga's. I wanted to check in with you one last time before I stop "
                f"bugging you! Should I go ahead and close your file on {it}, or would you like me to keep it "
                f"open?\n\nAnd if you ended up going another direction, no hard feelings at all!\n\n{SIGN}")
        body = (f"{hi}\n\nI wanted to check in one last time before I stop bugging you! Should I go ahead and "
                f"close your file on {it}, or would you like me to keep it open?\n\n"
                f"And if you ended up going another direction, no hard feelings at all.\n\n{SIGN}")
    return {"text": text, "email_subject": "Following up on your Zinga's estimate", "email_body": body}
