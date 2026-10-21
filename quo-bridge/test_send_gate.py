import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from send_gate import (
    AUTO_SEND_UNLOCK_STREAK,
    AutoSendStats,
    OutgoingText,
    decide,
    money_terms,
    waiting_status,
)

INDY = ZoneInfo("America/Indiana/Indianapolis")
CHICAGO = "America/Chicago"


def at(hour, minute=0, day=21, tz=INDY):
    # 2026-10-21 is a Wednesday.
    return datetime(2026, 10, day, hour, minute, tzinfo=tz)


def earned(category):
    stats = AutoSendStats(category)
    for _ in range(AUTO_SEND_UNLOCK_STREAK):
        stats.record_approval(edited=False)
    return stats


def text(body="Running about 10 minutes behind, see you soon!", category="on_my_way",
         tz="America/Indiana/Indianapolis", prospect="a0X123", dnc=False, approved=False):
    return OutgoingText(body, category, tz, prospect, dnc, approved)


class NeverRules(unittest.TestCase):
    def test_confirmation_blocked_even_when_approved(self):
        d = decide(text("See you Thursday at 2!", "confirmation", approved=True), at(10))
        self.assertEqual(d.action, "block")

    def test_do_not_contact_blocked_even_when_approved(self):
        d = decide(text(dnc=True, approved=True), at(10))
        self.assertEqual(d.action, "block")

    def test_empty_text_blocked(self):
        self.assertEqual(decide(text("   ", approved=True), at(10)).action, "block")

    def test_unknown_time_zone_blocked(self):
        self.assertEqual(decide(text(tz="Mars/Base", approved=True), at(10)).action, "block")

    def test_naive_time_rejected(self):
        with self.assertRaises(ValueError):
            decide(text(approved=True), datetime(2026, 10, 21, 10))


class QuietHours(unittest.TestCase):
    def test_approved_inside_window_sends(self):
        self.assertTrue(decide(text(approved=True), at(10)).may_send_now)

    def test_approved_at_9pm_waits_until_8am(self):
        d = decide(text(approved=True), at(21))
        self.assertEqual(d.action, "hold")
        self.assertEqual(d.send_after, at(8, day=22))

    def test_approved_at_6am_waits_until_8am_same_day(self):
        d = decide(text(approved=True), at(6))
        self.assertEqual(d.send_after, at(8))

    def test_window_uses_customer_time_zone(self):
        # 8:30am in Indianapolis is 7:30am in Chicago: too early there.
        d = decide(text(tz=CHICAGO, approved=True), at(8, 30))
        self.assertEqual(d.action, "hold")

    def test_exactly_8pm_is_outside(self):
        self.assertEqual(decide(text(approved=True), at(20)).action, "hold")


class AutoSend(unittest.TestCase):
    def test_earned_on_my_way_sends_by_itself(self):
        d = decide(text("Running about 10 minutes behind, see you soon."), at(10), earned("on_my_way"))
        self.assertEqual(d.action, "send", d.reasons)

    def test_not_yet_earned_needs_approval(self):
        stats = AutoSendStats("on_my_way")
        for _ in range(AUTO_SEND_UNLOCK_STREAK - 1):
            stats.record_approval(edited=False)
        self.assertEqual(decide(text(), at(10), stats).action, "needs_approval")

    def test_followups_always_need_approval(self):
        d = decide(text("Hi Sarah, checking in on the quote.", "followup"), at(10), earned("followup"))
        self.assertEqual(d.action, "needs_approval")

    def test_stats_for_other_category_do_not_count(self):
        d = decide(text(category="acknowledgment"), at(10), earned("on_my_way"))
        self.assertEqual(d.action, "needs_approval")

    def test_unmatched_customer_needs_approval(self):
        d = decide(text(prospect=None), at(10), earned("on_my_way"))
        self.assertEqual(d.action, "needs_approval")

    def test_auto_send_outside_window_needs_approval(self):
        self.assertEqual(decide(text(), at(21), earned("on_my_way")).action, "needs_approval")

    def test_long_text_needs_approval(self):
        self.assertEqual(decide(text("ok " * 200), at(10), earned("on_my_way")).action, "needs_approval")

    def test_money_blocks_auto_send(self):
        for body in [
            "Got it, I can do $200 off.",
            "Sure, 10% off if you sign this week.",
            "I can knock two hundred dollars off.",
            "Good news, fifteen percent off this month.",
            "Your total is 4,250 with install.",
            "We could do about 5k for the patio.",
            "Ask me about our discount.",
            "Financing is no interest for 12 months.",
            "Happy to sharpen the price a bit.",
        ]:
            with self.subTest(body=body):
                d = decide(text(body, "acknowledgment"), at(10), earned("acknowledgment"))
                self.assertEqual(d.action, "needs_approval")
                self.assertTrue(any("money" in r.lower() for r in d.reasons))

    def test_approved_money_text_sends(self):
        # Gerrit typed or approved it himself, so the money check does not apply.
        self.assertTrue(decide(text("Your quote total is $4,250.", "reply", approved=True), at(10)).may_send_now)

    def test_edit_turns_auto_send_off(self):
        stats = earned("acknowledgment")
        stats.record_approval(edited=True)
        self.assertFalse(stats.enabled)
        self.assertEqual(stats.approvals_in_a_row_unedited, 0)

    def test_complaint_turns_auto_send_off(self):
        stats = earned("acknowledgment")
        stats.record_complaint()
        self.assertFalse(stats.enabled)


class MoneyWords(unittest.TestCase):
    def test_plain_ack_has_no_money(self):
        for body in [
            "Got it, I'll get that over to you today.",
            "Thanks Sarah, I'll send the quote over this afternoon.",
            "Running 10 minutes behind, see you soon.",
            "Perfect, talk soon.",
        ]:
            with self.subTest(body=body):
                self.assertEqual(money_terms(body), [])


class Escalation(unittest.TestCase):
    def test_under_ten_minutes_ok(self):
        self.assertEqual(waiting_status(at(13), at(13, 9), handled=False), "ok")

    def test_ten_minutes_escalates(self):
        self.assertEqual(waiting_status(at(13), at(13, 10), handled=False), "escalate")

    def test_two_hours_missed(self):
        self.assertEqual(waiting_status(at(13), at(15), handled=False), "missed")

    def test_handled_is_ok(self):
        self.assertEqual(waiting_status(at(13), at(16), handled=True), "ok")

    def test_overnight_does_not_count(self):
        # Drafted at 11pm, checked at 11:30pm: no work time has passed.
        self.assertEqual(waiting_status(at(23), at(23, 30), handled=False), "ok")
        # Same draft at 8:10am next day: 10 work minutes.
        self.assertEqual(waiting_status(at(23), at(8, 10, day=22), handled=False), "escalate")

    def test_weekend_does_not_count(self):
        # Saturday 10am to Saturday 4pm (2026-10-24).
        self.assertEqual(waiting_status(at(10, day=24), at(16, day=24), handled=False), "ok")


if __name__ == "__main__":
    unittest.main()
