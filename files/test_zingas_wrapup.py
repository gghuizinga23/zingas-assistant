"""End-of-day wrap-up (F3): Val reads the day's visits and results herself and says what she does next."""

import json
import os
import tempfile
import unittest
from datetime import date, datetime

import zingas_wrapup as zw


def at(y, mo, d, h=19):
    return datetime(y, mo, d, h, 0, tzinfo=zw.TZ)


def visit(aid, result="", name="Pat Lee", phone="3175550101", email="pat@example.com", time="10:00",
          product="Shades", pid="0011234567"):
    return {"appointmentId": aid, "prospectId": pid, "time": time, "product": product, "result": result,
            "resultDetail": "", "customer": {"name": name, "phone": phone, "email": email, "city": "Carmel"}}


class WrapupTests(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp()

    def f0(self, customers):
        os.makedirs(os.path.join(self.vault, "followups"))
        with open(os.path.join(self.vault, "followups", "state.json"), "w") as fh:
            json.dump({"customers": {c["email"]: c for c in customers}}, fh)

    def block(self, now, days):
        return zw.brief_block(now, self.vault, read_day=lambda d: days.get(d, {"visits": []}))

    def test_mornings_say_nothing(self):
        self.assertEqual(zw.brief_block(at(2026, 10, 27, 8), self.vault, read_day=lambda d: None), "")

    def test_sold_quoted_and_no_show_lines(self):
        self.f0([{"email": "amy@example.com", "phone": "", "status": "active",
                  "touches": {"48 hours": {"due": "2026-10-29T14:00:00-04:00", "state": "planned"}}}])
        day = date(2026, 10, 27)
        out = self.block(at(2026, 10, 27), {day: {"visits": [
            visit("a1", "Sold", name="Pat Lee"),
            visit("a2", "Demoed, Not Sold", name="Amy Cole", email="amy@example.com", phone="3175550102"),
            visit("a3", "No Show", name="Bo Diaz", email="bo@example.com", phone="3175550103")]}})
        self.assertIn("WRAP-UP STARTS", out)
        self.assertIn("Today's visits (3):", out)
        self.assertIn("Pat Lee, Carmel (Shades): Sold. After the install", out)
        self.assertIn("Amy Cole, Carmel (Shades): Quoted. Follow-ups are on: the 48 hours touch on Thu Oct 29.", out)
        self.assertIn("Bo Diaz, Carmel (Shades): No Show. Nothing for Val to do.", out)
        self.assertNotIn("?", out.split("STARTS", 1)[1].replace("never copy this line", ""))   # never asks

    def test_quoted_without_estimate_email(self):
        out = self.block(at(2026, 10, 27), {date(2026, 10, 27): {"visits": [visit("a1", "Demoed, Not Sold")]}})
        self.assertIn("Val has not seen the estimate email yet", out)

    def test_recorded_visit_points_to_the_note(self):
        os.makedirs(os.path.join(self.vault, "visits", "0011234567"))
        open(os.path.join(self.vault, "visits", "0011234567", "2026-10-27-abc.md"), "w").close()
        out = self.block(at(2026, 10, 27), {date(2026, 10, 27): {"visits": [visit("a1", "Sold")]}})
        self.assertIn("Recorded on Plaud", out)

    def test_a_visit_shows_once_after_its_result(self):
        days = {date(2026, 10, 27): {"visits": [visit("a1", "Sold")]}}
        self.assertIn("Sold", self.block(at(2026, 10, 27), days))
        self.assertEqual(self.block(at(2026, 10, 27, 20), days), "")

    def test_no_result_is_checked_again_and_shows_when_it_comes(self):
        days = {date(2026, 10, 27): {"visits": [visit("a1", "")]}}
        self.assertIn("no result in Salesforce yet", self.block(at(2026, 10, 27), days))
        self.assertEqual(self.block(at(2026, 10, 28), days), "")       # still empty: quiet
        days[date(2026, 10, 27)] = {"visits": [visit("a1", "Sold")]}
        out = self.block(at(2026, 10, 29), days)
        self.assertIn("Earlier visits:", out)
        self.assertIn("Tue: 10am Pat Lee", out)

    def test_gives_up_after_three_evenings(self):
        days = {date(2026, 10, 27): {"visits": [visit("a1", "")]}}
        self.block(at(2026, 10, 27), days)
        self.block(at(2026, 10, 28), days)
        self.block(at(2026, 10, 29), days)
        out = self.block(at(2026, 10, 30), days)
        self.assertIn("still no result in Salesforce. Val stops checking.", out)
        self.assertEqual(self.block(at(2026, 10, 31), days), "")

    def test_monday_also_covers_saturday(self):
        days = {date(2026, 10, 24): {"visits": [visit("s1", "Sold", name="Sat Customer")]},
                date(2026, 10, 26): {"visits": [visit("m1", "Sold", name="Mon Customer")]}}
        out = self.block(at(2026, 10, 26), days)
        self.assertIn("Saturday's visits (1):", out)
        self.assertIn("Today's visits (1):", out)
        self.assertLess(out.index("Saturday"), out.index("Today"))

    def test_website_down_says_so_and_never_fails(self):
        out = zw.brief_block(at(2026, 10, 27), self.vault, read_day=lambda d: None)
        self.assertIn("could not read Tuesday's visits", out)

    def test_no_prices_even_if_the_website_slipped_one(self):
        v = visit("a1", "Sold", product="Shades")
        v["quotedAmount"] = 4200
        out = self.block(at(2026, 10, 27), {date(2026, 10, 27): {"visits": [v]}})
        self.assertNotIn("4200", out)
        self.assertNotIn("$", out)


if __name__ == "__main__":
    unittest.main()
