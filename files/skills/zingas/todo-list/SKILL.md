---
name: todo-list
description: Gerrit's running to-do list. How new emails, texts, calls and voicemails become tasks, how to rank them, and how to change the list when Gerrit asks.
version: 0.1.0
author: Zinga's Assistant
metadata:
  hermes:
    tags: [Zingas, To-do, Priorities, Briefs]
---

# Gerrit's to-do list

Gerrit's to-do list is kept by plain programs on this computer and by you, through one command: `zingas-todo`. The list lives in the vault (`todo/todo.json`, shown as `To-Do.md`). **Never edit those files directly.** Always use `zingas-todo`.

## How things get on the list by themselves
- **Emails:** `zingas-inbox` looks for new mail every 2 minutes, in every label and folder. It asks you to judge each new email, adds the task, and texts Gerrit in this chat.
- **Texts to the Quo number:** `zingas-quo` asks you for a draft reply and a task in the same answer.
- **Missed calls and voicemails to the Quo number:** a missed call with no voicemail becomes "Call back ..." for today. A voicemail comes with Quo's written transcript, and you judge it like an email. Calls Gerrit answered get a task only when Quo sends a call summary (Quo's Business plan).
- Gerrit's personal cell is never read. Only the Quo business number and work email.

## Judging one item
Ask: **does this need Gerrit to do something?** If not, `skip`.

Always `skip`:
- newsletters, promotions, vendor marketing, webinars
- automated notices (receipts, system alerts, calendar notices, Salesforce or RemodelerGo notices, "no-reply" senders), unless a real person is asking Gerrit for something in it
- appointment confirmations (corporate sends them)
- "thanks", "👍", "sounds good" and FYIs that ask for nothing
- anything already on the list: use `update` with that task's number instead of adding it twice

## Priority: what gets done first
| Priority | Use it when |
|---|---|
| `now` 🔴 | It hurts if it waits a few hours: a customer is upset or cancelling, a problem with an install or order, a same-day appointment issue, a signed job at risk, or an office or manager ask due today |
| `today` 🟠 | A customer or lead is waiting on Gerrit: a question, a quote follow-up, a missed call or voicemail to return, a new lead. Also office paperwork that holds up a deposit or an order (result an appointment, upload a contract) |
| `week` 🟡 | Office, HR and admin asks with no near deadline, vendor or rep requests, documents to send that block nothing |
| `later` ⚪ | Worth remembering but can wait: nice-to-dos, training, far-off meetings |

Ties: customer money first, then a customer waiting, then the office.

- `due` only when the item gives a date or a day ("by Friday" means the coming Friday's date). **Never invent a date.**
- `emergency: true` only for a real emergency that can't wait for the morning: the install crew did not show up, or a customer is cancelling a signed job. This is what lets a note go out after 8pm or on a weekend.

## Writing the task
- Start with a verb. 12 words or less. The person goes in `who` ("Pat Lee", "Beth, Payments").
- Good: "Result the Lee appointment and upload the contract". "Call back about motorized shades".
- `why`: one short line only when the priority needs a reason ("Holding up their deposit"). Otherwise empty.
- Facts only from the item. No prices or amounts.

## When Gerrit asks you in Telegram
Run the command, then answer with only what changed. Nothing extra.
| Gerrit says | You run |
|---|---|
| "What's on my list?" / "to-do list" | `zingas-todo list` and send it as is |
| "Add: order samples for Lee, this week" | `zingas-todo add "Order samples for the Lees" --priority week` |
| "Done 3" / "finished the Lee one" | `zingas-todo done 3` (run `zingas-todo list` first if you need the number) |
| "Move 4 to later" | `zingas-todo set 4 --priority later` |
| "4 is due Friday" | `zingas-todo set 4 --due YYYY-MM-DD` |
| "Take 5 off, not needed" | `zingas-todo drop 5` |
| "Oops, 3 isn't done" | `zingas-todo undo 3` |

Task numbers stay the same while a task is open, so "done 3" always means the same task. If Gerrit says a task is done and you can't tell which one, ask with the two closest matches.

When you handle something on the list yourself (you saved the draft Gerrit asked for), say so and ask "Mark 3 done?" only if it isn't obvious. Never mark a task done that needs Gerrit (a call, an upload, a send).

## In the briefs
Every morning and evening brief has the list (skill `briefs`): run `zingas-todo brief --since <time of the last brief>` and put its output in the brief.
