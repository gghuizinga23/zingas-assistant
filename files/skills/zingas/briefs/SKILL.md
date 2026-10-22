---
name: briefs
description: Gerrit's morning brief (8:00am) and evening brief (7:00pm), Monday to Friday, Indianapolis time. Every brief has the to-do list.
version: 0.1.0
author: Zinga's Assistant
metadata:
  hermes:
    tags: [Zingas, Briefs, To-do, Email]
---

# Morning and evening briefs

Two timed jobs write these on weekdays: the morning brief at 8:00am and the evening brief at 7:00pm (Indianapolis). Your answer is sent to Gerrit's Telegram as is, so write only the brief. No greeting before it, no sign-off after it.

## The to-do list is always in it
Right before you start, a program puts Gerrit's to-do list in your instructions, between the line `--- TO-DO LIST STARTS` and the line `--- TO-DO LIST ENDS`. **Copy the lines between them into the brief exactly as written** (never the two marker lines), every time, even when it says nothing is open. Don't re-sort it, re-number it, reword it or leave tasks out. Tasks marked 🆕 came in since the last brief (for example overnight, while notes were held for quiet hours). Never edit the list files.

## Morning brief
```
🪟 Morning brief: <one short line: how many things need Gerrit today, and the top one>

<the to-do list block, as written>

<Email: only if something isn't on the list yet, see below>

Idea: <at most 2 ideas, each on its own line>
```

## Evening brief
```
🪟 Evening brief: <one short line: what got done today, what's still open>

<the to-do list block, as written>

<Email: only if something isn't on the list yet>

Idea: <at most 2 ideas>
```
- In the evening, the "✅ Done since the last brief" line is the day's wins. Say it plainly in the first line ("You did 5 tasks today. 3 tasks are open. 1 task is due today.").
- Point out any task that says "due today" or "overdue" in the first line.

## The 24-hour rule (both briefs)
Every message must be answered within 24 hours (Gerrit's hard rule, skill `todo-list`). If any task says "⚠️ past 24 hours", the brief's first line says how many and names the oldest one ("⚠️ 3 messages are past 24 hours. The oldest is from Amy Cole."). Then say which ones have a draft ready. Never leave this out.

## Email check (both briefs)
New work email is already put on the list by `zingas-inbox` every 2 minutes. So the brief does **not** list emails again. Use skill `email-triage` only to look for:
- a customer or office email from the last 24 hours that asks Gerrit for something and is **not** on the list (the watcher can miss one). Add one line: "Email: <who> asked <what>. Do you want this on your list?" Never add it yourself.
- reply drafts you saved in Gmail Drafts that Gerrit hasn't sent. One line: "Drafts in Gmail that you did not send: 2 (Pat Lee, Beth)."
Skip this part when there's nothing. Never quote an email. Say what is needed in a few plain words.

## Ideas
Only here, at the end, each line starting with "Idea:". At most 2. Only facts you know (the list, email, customer notes). No made-up dates, prices or numbers. Skip ideas when you have none.

## Writing rules
- Write the brief in ASD-STE100 (skill `ste-writing`). The to-do list block is copied as is.
- Plain words, short lines. A 6th grader reads it at a glance.
- Synopses, never pasted customer words.
- No prices or amounts. No day counts you typed yourself (the list shows due dates).
- About 25 lines at most. If the list is long, it's still copied in full; keep everything else shorter.
- You can't send anything to a customer from a brief. Drafts still go through Gerrit's Approve tap.
