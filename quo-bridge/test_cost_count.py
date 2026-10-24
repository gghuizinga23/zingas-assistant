"""Tests for cost_count.py: quo-bridge's hourly text count for the website's Cost tab. No network: the
website is a fake opener and the records are in MemoryStore."""

import io
import json
import os
import re
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone

import cost_count as cc
from store import MemoryStore
from test_bridge import Rig

HERE = os.path.dirname(os.path.abspath(__file__))
NOW = datetime(2026, 10, 24, 16, 0, tzinfo=timezone.utc)     # Oct 24, noon in Indianapolis


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeWebsite:
    def __init__(self, status=200, reason=""):
        self.requests, self.status, self.reason = [], status, reason

    def __call__(self, req, timeout=None):
        body = json.loads(req.data)
        self.requests.append({"url": req.full_url, "method": req.get_method(), "headers": dict(req.header_items()),
                              "body": body, "timeout": timeout})
        if self.status == "down":
            raise urllib.error.URLError("no route")
        if self.status != 200:
            raise urllib.error.HTTPError(req.full_url, self.status, "x", {}, io.BytesIO(self.reason.encode()))
        return FakeResponse(json.dumps({"ok": True, "month": body["month"], "source": "quo-bridge"}).encode())


def sent(store, i, text, at, phone="+13175550123", final=None):
    store.insert_draft({"id": f"d{i}", "phone": phone, "body": text, "final_body": final, "status": "sent",
                        "sent_at": at.isoformat(), "category": "reply", "created_at": at.isoformat()})


class Segments(unittest.TestCase):
    def test_plain_text_is_160_a_part(self):
        self.assertEqual(cc.segments(""), 0)
        self.assertEqual(cc.segments("a" * 160), 1)
        self.assertEqual(cc.segments("a" * 161), 2)
        self.assertEqual(cc.segments("a" * 159 + "€"), 2)          # € takes two places in plain text

    def test_emoji_or_curly_quote_is_70_a_part(self):
        self.assertEqual(cc.segments("Hi! Thursday at 2 works great. 🙂"), 1)
        self.assertEqual(cc.segments("a" * 70), 1)
        self.assertEqual(cc.segments("a" * 68 + "🙂"), 1)          # an emoji takes two places: 70
        self.assertEqual(cc.segments("a" * 69 + "🙂"), 2)          # 71
        self.assertEqual(cc.segments("We’ll " + "a" * 70), 2)      # a curly apostrophe is not plain text


class Count(unittest.TestCase):
    def test_counts_texts_sent_this_month_only(self):
        s = MemoryStore()
        sent(s, 1, "a" * 161, datetime(2026, 10, 2, 15, tzinfo=timezone.utc))                     # 2 parts
        sent(s, 2, "draft", datetime(2026, 10, 3, 15, tzinfo=timezone.utc), final="Edited 🙂")      # 1 part
        sent(s, 3, "Sept", datetime(2026, 10, 1, 3, tzinfo=timezone.utc))      # 11pm Sept 30 in Indianapolis
        sent(s, 4, "", datetime(2026, 10, 4, 15, tzinfo=timezone.utc))          # email-only follow-up
        sent(s, 5, "no phone", datetime(2026, 10, 4, 15, tzinfo=timezone.utc), phone="")
        rows = s.sent_drafts_since(cc.utc_iso(cc.month_start("2026-09")))
        self.assertEqual(set(rows[0]), {"phone", "body", "final_body", "sent_at"})      # nothing else is read
        count = cc.make_count(rows, "2026-10", NOW)
        self.assertEqual(count["results"], {"texts": 2})
        line = count["services"][0]
        # Paid from the prepaid credits (Val counts the top-up), so it adds nothing; the name says what was used.
        self.assertEqual((line["billed"], line["runRate"]), (0.0, 0.0))
        self.assertEqual(line["name"], "Quo texts ($0.03 so far, paid from prepaid credits)")
        self.assertEqual(cc.make_count(rows, "2026-09", NOW)["results"], {"texts": 1})

    def test_matches_the_connections_example_exactly(self):
        with open(os.path.join(HERE, "..", "docs", "CONNECTIONS.md")) as fh:
            doc = fh.read()
        example = json.loads(re.search(r"quo-bridge sends only its own lines, for example\s*`(\{.*?\})`",
                                       doc, re.S).group(1))
        count = cc.make_count([], "2026-10", NOW)
        self.assertEqual(set(count), set(example))
        self.assertEqual(set(count["services"][0]), set(example["services"][0]))
        self.assertEqual({k: count["services"][0][k] for k in ("id", "kind", "billed", "runRate", "basis")},
                         {k: example["services"][0][k] for k in ("id", "kind", "billed", "runRate", "basis")})
        self.assertEqual(cc.make_count([{"phone": "+1", "body": "x" * 160 * 347, "final_body": None,
                                         "sent_at": "2026-10-10T12:00:00Z"}], "2026-10", NOW)["services"][0]["name"],
                         example["services"][0]["name"])
        self.assertEqual(set(count["results"]), set(example["results"]))
        self.assertEqual(count["services"][0]["billed"], 0)          # none sent is a real zero, not unknown

    def test_months(self):
        self.assertEqual(cc.open_months(NOW), ["2026-10"])
        self.assertEqual(cc.open_months(datetime(2026, 11, 7, 12, tzinfo=timezone.utc)), ["2026-11", "2026-10"])
        self.assertEqual(cc.month_end("2026-12"), datetime(2027, 1, 1, tzinfo=cc.TZ))


class Hourly(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.site = FakeWebsite()
        self.poster = cc.CostPoster("https://os.example.test/", "bridge-key", opener=self.site)
        sent(self.store, 1, "Thanks!", datetime(2026, 10, 20, 15, tzinfo=timezone.utc))

    def test_posts_with_quo_bridges_own_key(self):
        self.assertEqual(cc.hourly(self.store, self.poster, NOW), "posted")
        r = self.site.requests[0]
        self.assertEqual((r["method"], r["url"]), ("POST", "https://os.example.test/api/assistant/cost"))
        self.assertEqual(r["headers"]["Authorization"], "Bearer bridge-key")
        self.assertEqual(r["body"]["results"], {"texts": 1})
        self.assertEqual(self.store.events[-1]["kind"], "cost_posted")
        self.assertNotIn("+1317", json.dumps(self.store.events) + json.dumps(r["body"]))

    def test_once_an_hour(self):
        cc.hourly(self.store, self.poster, NOW)
        self.assertEqual(cc.hourly(self.store, self.poster, NOW + timedelta(minutes=59)), "not yet")
        self.assertEqual(cc.hourly(self.store, self.poster, NOW + timedelta(minutes=60)), "posted")
        self.assertEqual(len(self.site.requests), 2)

    def test_refused_or_down_tries_again_after_10_minutes(self):
        self.site.status, self.site.reason = 400, "month must be 2026-10."
        self.assertEqual(cc.hourly(self.store, self.poster, NOW), "failed")
        self.assertIn("HTTP 400: month must be", self.store.events[-1]["detail"])
        self.assertEqual(cc.hourly(self.store, self.poster, NOW + timedelta(minutes=9)), "waiting to try again")
        self.site.status = "down"
        self.assertEqual(cc.hourly(self.store, self.poster, NOW + timedelta(minutes=10)), "failed")
        self.site.status = 200
        self.assertEqual(cc.hourly(self.store, self.poster, NOW + timedelta(minutes=20)), "posted")

    def test_first_post_of_a_month_closes_last_month(self):
        cc.hourly(self.store, self.poster, NOW)
        nov2 = datetime(2026, 11, 2, 14, tzinfo=timezone.utc)
        sent(self.store, 2, "Morning!", datetime(2026, 11, 2, 13, tzinfo=timezone.utc))
        cc.hourly(self.store, self.poster, nov2)
        self.assertEqual([(r["body"]["month"], r["body"]["results"]["texts"]) for r in self.site.requests],
                         [("2026-10", 1), ("2026-10", 1), ("2026-11", 1)])
        cc.hourly(self.store, self.poster, nov2 + timedelta(hours=1))
        self.assertEqual(self.site.requests[-1]["body"]["month"], "2026-11")
        self.assertEqual(len(self.site.requests), 4)

    def test_off_without_the_website_settings(self):
        self.assertEqual(cc.hourly(self.store, None, NOW), "off")

    def test_a_broken_store_never_raises(self):
        class Broken(MemoryStore):
            def sent_drafts_since(self, since):
                raise RuntimeError("Supabase down")
        b = Broken()
        self.assertEqual(cc.hourly(b, self.poster, NOW), "failed")
        self.assertEqual(b.events[-1]["detail"], "RuntimeError")


class InTheTick(unittest.TestCase):
    def test_tick_posts_the_count_and_a_failure_never_stops_a_send(self):
        r = Rig(now=datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc))      # 9pm: an approved text waits
        site = FakeWebsite(status="down")
        r.bridge.cost = cc.CostPoster("https://os.example.test", "bridge-key", opener=site)
        _, d = r.draft()
        r.tap("a", d["id"])
        r.clock.t = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)       # 8am: it goes out
        status, done = r.bridge.tick()
        self.assertEqual((status, done["sent_or_held"], done["cost_count"]), (200, 1, "failed"))
        self.assertEqual(len(r.quo.sent), 1)
        site.status = 200
        r.clock.t += timedelta(minutes=10)
        self.assertEqual(r.bridge.tick()[1]["cost_count"], "posted")
        self.assertEqual(site.requests[-1]["body"]["results"], {"texts": 1})


if __name__ == "__main__":
    unittest.main()
