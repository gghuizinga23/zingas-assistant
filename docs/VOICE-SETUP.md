# Teaching Val Gerrit's voice (one-time read, chosen 2026-10-21)

Gmail waits for Delisa, so this starts with Gerrit's old **customer** texts on this Mac.

## What exists today
- Fixed rules: `files/skills/zingas/zingas-voice/SKILL.md` (from spec §3).
- `VOICE.md` and the example bank (`voice-examples/`) don't exist yet. Val's voice skill expects both.
- `sent-messages.log` has 36 lines, mostly system texts to Gerrit, so it isn't useful here.
- `dashboard/imessage.py` already reads Messages read-only. It needs Full Disk Access.

## The one-time read (needs Gerrit's OK first)
1. Only threads whose phone number matches a customer in the Salesforce exports. Personal texts are
   never opened: the filter runs on phone numbers before any message text is read.
2. Only Gerrit's own sent texts from the last 12 months, plus the customer line they answer.
3. Runs on this Mac only. Read only: nothing is sent, changed or deleted.
4. Names, phone numbers, emails and street addresses become [Name], [Phone], [Email], [Address].
5. From the cleaned texts I write `VOICE.md`: Gerrit's real phrases, openers, sign-offs, and how
   Gerrit handles price, spouse and competitor questions. It holds no customer names.
6. 30 to 50 cleaned examples go to `voice-examples/`.
7. Gerrit reads `VOICE.md` and says yes before it goes to Val's computer.
8. Nothing here goes into git. The cleaned files stay in a git-ignored folder on this Mac until
   they're copied to Val.
9. After this, the Messages reader is retired (plan: the personal cell is not read live).

Later, when Gmail works: the same for 12 months of sent work email.

## Status 2026-10-21
- Done: the one-time read. 176 customer threads, 464 of Gerrit's texts kept, all cleaned
  (no names, phone numbers, emails, addresses, places or dollar amounts left).
- Written, in the git-ignored `voice-work/` folder: `VOICE.md` (Gerrit's openers, sign-off, phrases,
  tone, and what Gerrit does in 10 situations) and `voice-examples.md` (45 examples, 18 situations).
- Gerrit said yes. Copied to Val's computer, root-only: `/root/Documents/ZingasVault/VOICE.md` and
  `voice-examples/gerrit-texts.md` (fingerprints match this Mac's copies).
- **The one-time reader is retired.** The script that read Messages is deleted. Nothing reads texts
  on a timer (no scheduled tasks, no cron, no launch agents for it). Val never reads the personal cell.
- Still on this Mac: the old dashboard's `promises.py` can read Messages if someone runs it by hand.
  It doesn't run on its own.
