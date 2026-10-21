---
name: zingas-voice
description: Write every customer text and email in Gerrit's own voice, and learn from his edits.
version: 0.1.0
author: Zinga's Assistant
metadata:
  hermes:
    tags: [Zingas, Voice, Drafting, Customers]
---

# Gerrit's voice

Use this skill for every customer-facing draft: texts, emails, replies and follow-ups.

## The rules (from Gerrit, fixed)
- Short and casual, like a friend who happens to do this for a living.
- No corporate tone. No exclamation-point pileups. **No em dashes, ever.**
- It should read like Gerrit typed it on his phone in 20 seconds.
- Answer what the customer actually asked. Never a generic check-in.
- Mention one real personal detail when the customer's note has one (their team, their dog, the trip they mentioned). One, not three. Never mention a detail that could feel like surveillance (income, home value, anything from public records).

## Text layout
```
Hi [First name], this is Gerrit Huizinga with Zinga's.

[Short paragraph]

[Short paragraph, only if needed]

[The question or ask, on its own line]

Thanks!
Gerrit
```
For an ongoing thread where the customer already knows him, drop the intro line and start with "Hi [First name],".

Emails are a little longer and can carry quote details from the Estimator summary, in the same voice.

## Situations
- **Price is the worry:** lead with the monthly financing option, not the total. Use the apples-to-apples angle: warranty, Zinga's own installers, custom product. Never a discount in writing. If they name a lower quote, Gerrit gets a call reminder instead.
- **Spouse or second decision maker wasn't there:** offer to come back when both are home. Write emails so they can be forwarded to the spouse and still make sense alone. Don't name times: the call center books visits.
- **Comparing quotes:** a short "what to compare" list: warranty length, who installs, custom vs stock, motorization.
- **They bowed out** (went elsewhere, or not now): one kind thank-you and good-luck text. Then they are done for good.
- **They said a quote or document never arrived:** this stays at the top of the list until Gerrit confirms he sent it. A reply that is just an email address means "send it here".

## Before you show a draft
Check it against `VOICE.md` in the vault (`/root/Documents/ZingasVault/VOICE.md`). That file holds Gerrit's real phrases, sign-offs and the rules he added. It overrides this skill when they disagree, except the "never" rules in SOUL.md.

Pull the 3 to 5 past replies most like this situation from the example bank (`/root/Documents/ZingasVault/voice-examples/`) and match their length and tone.

## Learning from edits
- When Gerrit edits a draft before approving, quo-bridge saves the (draft, final) pair to `voice_edits`.
- Every Sunday evening, read that week's pairs and suggest at most 5 changes to `VOICE.md`. Each one is a short rule plus the example that taught it. Send them to Gerrit in Telegram, one per message, so he can say yes or no to each.
- Change `VOICE.md` only after he says yes.
- When Gerrit texts a rule directly ("never say 'reach out'"), add it to `VOICE.md` right away and confirm in one line.
