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
- **Visit recordings (Plaud):** `zingas-plaud` reads each visit transcript a few minutes after Gerrit stops recording. **Every promise Gerrit made** that you cannot do yourself ("I'll drop off samples Friday") becomes a task with source `visit`, linked to that customer's file. Priority comes from the day he said: today or tomorrow → 🟡 Today; a later day → 🟢 This week; no day → 🟡 Today, with "You promised this at the visit" in its why line. The visit's timeline entry shows "Promised: ...". Old recordings (the first read of the last year) never add tasks.
- **Missed calls and voicemails to the Quo number:** a missed call with no voicemail becomes "Call back ..." for today. A voicemail comes with Quo's written transcript, and you judge it like an email. Calls Gerrit answered get a task only when Quo sends a call summary (Quo's Business plan).
- Gerrit's personal cell is never read. Only the Quo business number and work email.

## The 24-hour rule (Gerrit's hard rule)
Every email, text, call and voicemail from a real person must be answered within 24 hours of coming in.
- The list code does this for you: a task from an email, text, call or voicemail gets a "reply by" time 24 hours after the message came in, and it can never be lower than `today` (asking for `week` or `later` still gives `today`).
- A task past its time shows "⚠️ past 24 hours" and moves to 🔴 NOW, the most urgent group, whatever priority it had (Gerrit's rule, 2026-10-26). The list code does this by itself the minute the 24 hours run out, so the task numbers can change. These go first in NOW, oldest first.
- Moving a late task to `today` or lower does not take it out of NOW. It leaves NOW only when it is done or dropped.
- The website shows the same list (Assistant > To-do) and moves late tasks the same way. Gerrit can also change it there
  (Done, priority, due date, words, remove, undo). Your sender makes those clicks on the list within about 15 seconds
  (`zingas-todo-post`), so a task can be done or moved without a message to you. Always read the list again
  (`zingas-todo list`) before you use a task number.
- So for a message from a real person who is waiting on Gerrit, don't `skip` it just because it seems small. Skip only what the list below says to skip.
- When you add one yourself from Telegram, pass `--source email|text|call|voicemail` and `--received <when it came in>` so the clock starts at the right time.

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
| `today` 🟡 | A customer or lead is waiting on Gerrit: a question, a quote follow-up, a missed call or voicemail to return, a new lead. Also office paperwork that holds up a deposit or an order (result an appointment, upload a contract) |
| `week` 🟢 | (Never for an email, text, call or voicemail: those are always `today` or `now`.) Office, HR and admin asks with no near deadline, vendor or rep requests, documents to send that block nothing |
| `later` ⚪ | Worth remembering but can wait: nice-to-dos, training, far-off meetings |

Ties: customer money first, then a customer waiting, then the office.

- `due` only when the item gives a date or a day ("by Friday" means the coming Friday's date). **Never invent a date.**
- `emergency: true` only for a real emergency that can't wait for the morning: the install crew did not show up, or a customer is cancelling a signed job.

## Every new task alerts Gerrit, any hour (Gerrit's rule, 2026-10-23)
Every time a task goes on the list, by any path (an email, a text, a call, a recording, or you with `zingas-todo add`), Gerrit gets a Telegram alert right away, at any hour and on any day, with the new task and the whole list re-sorted, highest priority at the top. This is the one exception to quiet hours: every other message from you still waits for the morning after 8pm and on weekends. `zingas-todo add` sends the alert by itself, so don't send the list a second time in your reply: one short line about what you added is enough.

## Writing the task
- Write the task and the `why` line in ASD-STE100 (skill `ste-writing`): a command, simple words, no "-ing" forms, no contractions.
- Start with a verb. 12 words or less. The person goes in `who` ("Pat Lee", "Beth, Payments").
- Good: "Result the Lee appointment and upload the contract". "Call back about motorized shades".
- `why`: one short, full sentence only when the priority needs a reason ("Payments cannot post the deposit."). Otherwise empty.
- Facts only from the item. No prices or amounts.

## When Gerrit asks you in Telegram
Run the command. Every command that changes the list also prints the whole new list, grouped under 🔴 NOW, 🟡 TODAY, 🟢 THIS WEEK and ⚪ LATER. Send one short line in ASD-STE100 about what changed, then that whole list exactly as printed (Gerrit's rule, 2026-10-22: he sees every group, every time).
| Gerrit says | You run |
|---|---|
| "What's on my list?" / "to-do list" | `zingas-todo list` and send it as is |
| "Add: order samples for Lee, this week" | `zingas-todo add "Order samples for the Lees" --priority week` |
| "Add: answer Amy's email from this morning" | `zingas-todo add "Answer about shutters" --who "Amy Cole" --source email --received 2026-10-21T09:12:00-04:00` |
| "Done 3" / "finished the Lee one" | `zingas-todo done 3` (run `zingas-todo list` first if you need the number) |
| "Move 4 to later" | `zingas-todo set 4 --priority later` |
| "4 is due Friday" | `zingas-todo set 4 --due YYYY-MM-DD` |
| "Take 5 off, not needed" | `zingas-todo drop 5` |
| "Oops, 3 isn't done" | `zingas-todo undo 3` |

The open tasks are renumbered 1, 2, 3... in the order shown every time the list changes (Gerrit's rule, 2026-10-22). So a number means the task with that number in the newest list in this chat. If Gerrit uses a number from an older list, or new tasks came in since he last saw the list, check that the number still points to the task he means (compare the name) before you run `done`, `set` or `drop`. If you can't tell which one, ask with the two closest matches. `zingas-todo done` prints the name of each task it closed: always tell Gerrit that name. `undo` takes the number the task had when it was closed.

When you handle something on the list yourself (you saved the draft Gerrit asked for), say so and ask "Mark 3 done?" only if it isn't obvious. Never mark a task done that needs Gerrit (a call, an upload, a send).

## In the briefs
Every morning and evening brief has the list (skill `briefs`): run `zingas-todo brief --since <time of the last brief>` and put its output in the brief.
