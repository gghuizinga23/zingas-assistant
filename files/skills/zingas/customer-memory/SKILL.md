---
name: customer-memory
description: Match every text, email and recording to one Salesforce customer, and keep that customer's memory note.
version: 0.1.0
author: Zinga's Assistant
metadata:
  hermes:
    tags: [Zingas, Customers, Salesforce, Memory, Identity]
---

# Customer memory

## Step 1: match the person (do this before anything else)
Every customer is keyed on their **Salesforce Prospect ID**. Try in this order:
1. Phone number, normalized to E.164 (+1XXXXXXXXXX). Salesforce phone fields can hold two numbers; check both.
2. Email address, lowercased.
3. A Salesforce lookup by name and address, only to suggest a match. Never auto-match on name alone.

**One match:** use it.
**More than one match:** ask Gerrit in Telegram which one, showing name, address and appointment date for each.
**No match:**
- Create a stub note marked `unmatched` with what you know.
- Ask Gerrit in Telegram: "A new number sent a text to the business line: [first message]. Is this person a new lead or a person that you know?"
- Flag it in the evening brief.
- **No cadence, no memory updates and no drafts beyond a reply Gerrit asks for** until it is matched.

## Step 2: the memory note
One note per customer at `/root/Documents/ZingasVault/customers/<ProspectID>.md`, mirrored to the Supabase table `assistant.customer_memory`.

Keep:
- Both homeowner names (even if only one was home), and who decides
- Products and rooms quoted, the Estimator proposal ID and link (never the price unless Gerrit put it in a note)
- What they liked (fabric, color, feature) and what made them hesitate
- Primary objection: price, spouse missing, comparing quotes, or none
- Timing signals (moving, party, baby, summer)
- Competitors mentioned
- Personal details worth remembering (team, pet's name, kid's sport, upcoming trip)
- Do-not-contact flag, if set

## Rules
- Only add facts that came from a real source: Gerrit, the customer, a recording, Salesforce or the Estimator. Write where each fact came from.
- Never store anything from Gerrit's personal (non-work) life.
- If two sources disagree, keep both and ask Gerrit.
