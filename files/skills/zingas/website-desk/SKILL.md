---
name: website-desk
description: Gerrit uses Val from the company website too (Zinga's OS > Assistant). How website messages, question cards and settings reach Val (zingas-desk).
version: 0.1.0
author: Zinga's Assistant
metadata:
  hermes:
    tags: [Zingas, Website, Questions, Settings]
---

# Val's desk on the website

Gerrit's rule (2026-10-28): everything he does with you in Telegram he can also do on the website, from an iPad or a
computer. Telegram stays exactly as it is. The program `zingas-desk` (always on) carries it both ways.

## Messages from the website

- A message that starts with `[From the website]` is Gerrit, typing on Assistant > Talk to Val. It is the same
  conversation as Telegram. Answer it exactly as you would in Telegram, with the same tools and rules. Your answer
  is copied to Telegram and to the website by the program: don't send it again yourself.
- "Gerrit answered your question on the website" is his answer to a question card you made. Act on it as if he had
  said it in Telegram.

## Asking Gerrit a question with buttons

When you need a decision from Gerrit (not for every message), also put it on the website's Needs you list:

    echo "<the question, plain words, no prices>" | zingas-desk ask --id <kind>:<a short stable ref> --kind <kind> \
        --question-file - --option yes="Yes" --option no="No"        # up to 4 buttons
    ... --text                                                        # or let him type an answer

- Ask in Telegram as you always do too: he answers in whichever place he is.
- Use the same --id for the same question, so asking again doesn't make a second card.
- When it is settled some other way (he answered in Telegram), close the card: `zingas-desk close --id <id> --note "Answered in Telegram."`
- Customers by first name at most. Never a price, an amount or a phone number in a question.
- "Is this task done too?" after a Done is made by the to-do program itself, with Yes and No: don't make it yourself.

## Settings Gerrit changes on the website

Assistant > Settings and Follow-up rules. Your programs read them by themselves (`zingas-desk settings` shows them):
programs on or off, where each kind of note goes (Telegram, iPad, both or neither), his price and competitor answers
and his review link (written into your own files), the thank-you's wait for the recording, the call-back hours, and
each follow-up's day, on or off, text and email or only one, the quiet days after a reply and the list time.

- When Gerrit changes one of these in Telegram, change it the usual way (zingas-answers, zingas-installs set ...) and
  tell him it shows on the website after his next change there; the website keeps its own copy.
- "Pause all customer texts" is in quo-bridge, not yours: when he asks you to pause, point him to Assistant > Settings
  (or the 🛑 in Telegram cards). Never try to send around it.
