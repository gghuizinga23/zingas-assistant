---
name: followup-cadence
description: Decide who gets a follow-up text today after an in-home appointment, using Gerrit's fixed two-touch cadence.
version: 0.1.0
author: Zinga's Assistant
metadata:
  hermes:
    tags: [Zingas, Follow-up, Cadence, Salesforce]
---

# Follow-up cadence

Gerrit set this on 9/2. Do not add steps back.

## Who is in the cadence
Only appointments Gerrit ran and resulted in Salesforce (through RemodelerGo):
- **Sold:** no follow-up sequence.
- **Demo, not sold (quoted):** cadence starts.
- **Not demoed because the decision maker was missing:** cadence starts, aimed at a return visit (the call center books it).
- **Rescheduled:** nothing sends. The clock restarts on the new date.
- **No show / canceled:** flag it in the morning brief for Gerrit to decide.

The customer must be matched to a Salesforce Prospect ID (skill `customer-memory`). If not, put them in "needs a match" in the brief and skip them.

## The two touches
| When | What |
|---|---|
| 48 hours after the appointment | Text: the direct ask, or the return-visit offer if the decision maker was missing |
| 7 days after the appointment | Text, **only if the customer has not replied since the visit**. Then stop |

The same day as the appointment there is also a "great to meet you" text. It must say the quote was emailed so they go find it. The truck debrief (skill `truck-debrief`, coming in Phase 4) will start it. Until then, draft it from the evening brief.

## Stop rules (checked every run)
- The customer replied: stop the cadence. Their message gets a reply draft instead.
- The customer signed, was marked lost, or is on the do-not-contact list: stop.
- More than 60 days since the appointment: stop.
- An unanswered ask older than 7 days drops off the list and is not chased.
- **Exception, never drop:** a customer waiting on a quote, estimate or promised document stays on the list until Gerrit confirms it was sent.

## Counting days
Count weekdays only for pace math. For the 48-hour and 7-day touches, use calendar time from the appointment, and send only between 8am and 8pm in the customer's time zone (quo-bridge enforces this).

## Output
For each customer due today: name, Prospect ID, which touch, one line of context from their note, and the draft (skill `zingas-voice`). Label each draft `followup`. Drafts go to the approvals queue. Once follow-ups have earned auto-send, quo-bridge may send them by itself after a 5-minute Stop countdown.
