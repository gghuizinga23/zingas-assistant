---
name: scheduling-handoff
description: When a customer wants to move or book an appointment, draft a reply and a request to the call center. Never change the calendar.
version: 0.1.0
author: Zinga's Assistant
metadata:
  hermes:
    tags: [Zingas, Scheduling, Call center]
---

# Scheduling handoff

The call center owns scheduling. You can read Gerrit's calendar. You never change it.

## When a customer asks to move, cancel or book
Example: "Can we do Thursday instead?"

Make **two drafts**, both sent to the approvals queue together. Label the customer reply `scheduling_handoff`: once that kind has earned auto-send, it may go by itself after a 5-minute Stop countdown. The call-center request always waits for Gerrit; mark it ⚠️ so it is seen right away. If the customer says "cancel" or sounds upset, quo-bridge sends both to Gerrit anyway.

1. **To the customer** (skill `zingas-voice`):
   > Hi Sarah, no problem. I'll have our scheduling team reach out to get you moved to Thursday. Thanks! Gerrit

   Do not promise a time. Do not say it is confirmed.

2. **To the call center** (a shared team, answered nearly all the time):
   - **Email (default):** appointments@zingashome.com. Make it a Gmail draft for Gerrit to send.
   - **Phone (backup):** (317) 339-1166. Only if Gerrit asks to call or text instead; show the request ready to copy.
   - Keep it short. They only need:
     - the customer's name
     - what the customer asked for, in their words
   - Never send it yourself.

## Never
- Never send an appointment confirmation. Corporate already sends them.
- Never edit, move or delete a calendar event.
