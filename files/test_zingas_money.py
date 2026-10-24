"""Tests for zingas_money.py: Val's hourly cost count. No network: the website is a fake opener, Hermes's
state.db is a small SQLite file made here, and the vault files are made-up numbers."""

import io
import json
import os
import re
import sqlite3
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta

import zingas_money as zm

HERE = os.path.dirname(os.path.abspath(__file__))
TZ = zm.TZ
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=TZ)          # Oct 24: 23.5 of 31 days gone
with open(os.path.join(HERE, "money_prices.json")) as fh:
    PRICES = json.load(fh)


def ts(*a):
    return datetime(*a, tzinfo=TZ).timestamp()


def usage(provider="nous", model="anthropic/claude-sonnet-5.5", first=None, last=None, **tokens):
    row = {"provider": provider, "model": model, "task": "", "input": 0, "output": 0, "cacheRead": 0,
           "cacheWrite": 0, "hermesCost": 0, "first": first or ts(2026, 10, 10), "last": last or ts(2026, 10, 10)}
    row.update(tokens)
    return row


def make_state_db(path, rows):
    """The parts of Hermes's real table (schema version 30, checked on Val's computer 2026-10-24)."""
    con = sqlite3.connect(path)
    con.execute("""create table session_model_usage (session_id text not null, model text not null,
        billing_provider text not null default '', billing_base_url text not null default '',
        billing_mode text not null default '', task text not null default '', api_call_count integer default 0,
        input_tokens integer default 0, output_tokens integer default 0, cache_read_tokens integer default 0,
        cache_write_tokens integer default 0, reasoning_tokens integer default 0,
        estimated_cost_usd real default 0, actual_cost_usd real default 0, cost_status text, cost_source text,
        first_seen real, last_seen real)""")
    for i, r in enumerate(rows):
        con.execute("insert into session_model_usage (session_id, model, billing_provider, task, input_tokens, "
                    "output_tokens, cache_read_tokens, cache_write_tokens, estimated_cost_usd, first_seen, last_seen) "
                    "values (?,?,?,?,?,?,?,?,?,?,?)",
                    (f"s{i}", r["model"], r["provider"], r.get("task", ""), r["input"], r["output"], r["cacheRead"],
                     r["cacheWrite"], r["hermesCost"], r["first"], r["last"]))
    con.commit()
    con.close()


SUBS = {"subscriptions": [
    {"id": "orgo", "name": "Orgo", "cost": 29, "cycle": "month", "nextRenewal": "2026-11-21",
     "receipts": [{"date": "2026-10-21", "amount": 29}], "lastUsed": "2026-10-24"},
    {"id": "nous", "name": "Nous Portal", "cost": 20, "cycle": "month", "plan": "plus", "nextRenewal": "2026-11-21"},
    {"id": "quo", "name": "Quo", "cost": 23, "cycle": "month", "nextRenewal": "2026-09-30"},
    {"id": "plaud", "name": "Plaud Unlimited", "cost": 240, "cycle": "year", "nextRenewal": "2027-09-21",
     "personal": True},
    {"name": "ChatGPT", "cost": 20, "personal": True, "lastUsed": "2026-08-01"},
    {"id": "Bad Id!", "name": "", "cost": 5},
    {"id": "broken", "name": "No price"},
]}


# ---------------------------------------------------------------- AI use

class AiUse(unittest.TestCase):
    def test_reads_hermes_token_counts(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "state.db")
            make_state_db(db, [usage(input=1000, output=2000, cacheRead=3000, cacheWrite=4000, hermesCost=0.05),
                               usage(first=ts(2026, 8, 1), last=ts(2026, 8, 2), input=5)])
            rows = zm.read_usage(db, since=datetime(2026, 9, 1, tzinfo=TZ))
        self.assertEqual(len(rows), 1)       # the August row is older than asked
        self.assertEqual((rows[0]["input"], rows[0]["output"], rows[0]["cacheRead"], rows[0]["cacheWrite"]),
                         (1000, 2000, 3000, 4000))
        self.assertEqual(rows[0]["provider"], "nous")

    def test_no_database_is_unknown_not_zero(self):
        self.assertIsNone(zm.read_usage("/nope/state.db"))
        count = zm.make_count("2026-10", NOW, PRICES, None, SUBS, None, None, None)
        nous = next(s for s in count["services"] if s["id"] == "nous")
        self.assertIsNone(nous["billed"])
        self.assertNotIn("credits", count)

    def test_price_table_then_hermes_guess_then_unknown(self):
        # 1M in, 1M out, 1M cache read, 1M cache write at $2 / $10 / $0.20 / $2.50
        r = usage(input=10**6, output=10**6, cacheRead=10**6, cacheWrite=10**6, hermesCost=99)
        self.assertAlmostEqual(zm.row_cost(r, PRICES), 14.70)
        self.assertEqual(zm.row_cost(usage(model="new-model", input=10, hermesCost=0.4), PRICES), 0.4)
        self.assertIsNone(zm.row_cost(usage(model="new-model", input=10), PRICES))
        self.assertEqual(zm.row_cost(usage(model="new-model"), PRICES), 0.0)

    def test_a_long_chat_is_split_across_months(self):
        r = usage(first=ts(2026, 9, 30, 12), last=ts(2026, 10, 1, 12), input=10**6)     # $2, half each side
        self.assertAlmostEqual(zm.ai_cost([r], PRICES, "nous", zm.month_start("2026-10"), NOW), 1.0)
        self.assertAlmostEqual(zm.ai_cost([r], PRICES, "nous", zm.month_start("2026-09"),
                                          zm.month_end("2026-09")), 1.0)

    def test_nous_is_the_plan_plus_use_over_22(self):
        under = [usage(output=10**6)]                      # $10 of use: inside the $22 included
        line = zm.ai_lines(under, PRICES, [], "2026-10", NOW)[0]
        self.assertEqual((line["id"], line["kind"], line["basis"]), ("nous", "ai", "estimate"))
        self.assertEqual(line["billed"], 20.0)
        self.assertEqual(line["runRate"], 20.0)            # $10 since Oct 10 is $21.38 a month: still included
        over = [usage(output=3 * 10**6)]                   # $30 of use: $8 over
        line = zm.ai_lines(over, PRICES, [], "2026-10", NOW)[0]
        self.assertEqual(line["billed"], 28.0)
        self.assertEqual(line["runRate"], round(20 + 30 / (14.5 / 31) - 22, 2))   # paced from Oct 10, the first use

    def test_pace_counts_from_the_first_use_this_month(self):
        self.assertAlmostEqual(zm.month_share("2026-10", NOW), 23.5 / 31)
        self.assertAlmostEqual(zm.month_share("2026-10", NOW, datetime(2026, 10, 21, 12, tzinfo=TZ)), 3 / 31)
        self.assertAlmostEqual(zm.month_share("2026-10", NOW, datetime(2026, 10, 24, 11, tzinfo=TZ)), 1 / 31)
        self.assertEqual(zm.month_share("2026-10", datetime(2026, 11, 2, tzinfo=TZ)), 1.0)

    def test_backup_brain_shows_only_when_used_and_adds_nothing(self):
        self.assertEqual([l["id"] for l in zm.ai_lines([usage()], PRICES, [], "2026-10", NOW)], ["nous"])
        lines = zm.ai_lines([usage(), usage(provider="anthropic", model="claude-sonnet-5-5", input=500)],
                            PRICES, [], "2026-10", NOW)
        backup = next(l for l in lines if l["id"] == "anthropic")
        self.assertEqual((backup["billed"], backup["runRate"]), (0.0, 0.0))


# ---------------------------------------------------------------- fixed plans

class Subscriptions(unittest.TestCase):
    def setUp(self):
        self.subs = zm.load_subscriptions(SUBS, NOW.date())

    def test_bad_rows_are_left_out_never_guessed(self):
        self.assertEqual([s["id"] for s in self.subs], ["orgo", "nous", "quo", "plaud", "chatgpt"])

    def test_lines(self):
        lines = {l["id"]: l for l in zm.subscription_lines(self.subs, "2026-10", skip={"nous"})}
        self.assertNotIn("nous", lines)                    # inside the AI line, never counted twice
        self.assertEqual((lines["orgo"]["billed"], lines["orgo"]["basis"]), (29.0, "receipt"))
        self.assertEqual((lines["quo"]["billed"], lines["quo"]["basis"]), (23.0, "estimate"))
        self.assertEqual(lines["plaud"]["billed"], 0.0)    # yearly, paid Sept 2026, renews Sept 2027
        self.assertTrue(lines["plaud"]["personal"])
        self.assertNotIn("personal", lines["orgo"])

    def test_yearly_plan_counts_in_the_month_it_was_paid(self):
        subs = zm.load_subscriptions({"subscriptions": [
            {"id": "plaud", "name": "Plaud", "cost": 240, "cycle": "year", "nextRenewal": "2027-10-21"}]}, NOW.date())
        self.assertEqual(zm.subscription_lines(subs, "2026-10", skip=set())[0]["billed"], 240.0)   # bought Oct 21
        self.assertEqual(zm.subscription_lines(subs, "2026-11", skip=set())[0]["billed"], 0.0)
        self.assertEqual(zm.subscription_lines(subs, "2027-10", skip=set())[0]["billed"], 240.0)   # renews

    def test_one_time_charges_count_only_in_the_month_paid(self):
        subs = zm.load_subscriptions({"subscriptions": [
            {"id": "quo-a2p-setup", "name": "Quo sign-up fee", "cost": 19.5, "cycle": "once",
             "nextRenewal": "2027-10-21", "receipts": [{"date": "2026-10-20", "amount": 19.5}]},
            {"id": "quo-credits", "name": "Quo text credits", "cost": 20, "cycle": "once", "kind": "texts",
             "receipts": [{"date": "2026-10-21", "amount": 20}, {"date": "2026-11-02", "amount": 20}]},
            {"id": "quo", "name": "Quo Business", "cost": 299.14, "cycle": "year", "nextRenewal": "2027-10-21",
             "receipts": [{"date": "2026-10-20", "amount": 299.14}]}]}, NOW.date())
        oct_ = {l["id"]: l for l in zm.subscription_lines(subs, "2026-10", skip=set())}
        self.assertEqual({k: (l["billed"], l["basis"]) for k, l in oct_.items()},
                         {"quo-a2p-setup": (19.5, "receipt"), "quo-credits": (20.0, "receipt"),
                          "quo": (299.14, "receipt")})
        self.assertEqual(oct_["quo-credits"]["kind"], "texts")
        nov = {l["id"]: l["billed"] for l in zm.subscription_lines(subs, "2026-11", skip=set())}
        self.assertEqual(nov, {"quo-credits": 20.0, "quo": 0.0})       # a second top-up; no fee again
        self.assertEqual([r["id"] for r in zm.subscriptions_list(subs)], ["quo"])   # nothing renews
        self.assertIsNone(zm.check_count({"month": "2026-10", "services": list(oct_.values()),
                                          "subscriptions": zm.subscriptions_list(subs)}, ["2026-10"]))

    def test_list_rolls_renewals_forward_and_marks_unused(self):
        rows = {r["id"]: r for r in zm.subscriptions_list(self.subs)}
        self.assertEqual(rows["quo"]["nextRenewal"], "2026-10-30")     # Sept 30 has passed
        self.assertIsNone(rows["chatgpt"]["nextRenewal"])
        self.assertTrue(rows["chatgpt"]["unused"])                    # not used since August
        self.assertFalse(rows["orgo"]["unused"])
        self.assertEqual(rows["plaud"]["cycle"], "year")

    def test_nous_plan_comes_from_the_vault_else_the_table(self):
        self.assertEqual(zm.nous_plan(PRICES, self.subs), (20, 22.0))
        self.assertEqual(zm.nous_plan(PRICES, []), (20.0, 22.0))


# ---------------------------------------------------------------- backups, credits, results

class Backblaze(unittest.TestCase):
    def test_nothing_before_the_first_backup(self):
        self.assertEqual(zm.backblaze({"last_error": "waiting for keys in 1Password"}, PRICES, "2026-10", NOW),
                         (None, None))

    def test_free_under_10_gb(self):
        line, limit = zm.backblaze({"last_ok": "2026-10-24T02:30:00-04:00", "last_ok_bytes": 2 * 10**8,
                                    "stored_bytes": 3 * 10**9}, PRICES, "2026-10", NOW)
        self.assertEqual((line["billed"], line["runRate"], line["basis"]), (0.0, 0.0, "count"))
        self.assertEqual(limit, {"name": "Backblaze", "used": 3.0, "limit": 10.0, "unit": "GB"})

    def test_over_10_gb_and_old_state_is_an_estimate(self):
        line, _ = zm.backblaze({"last_ok": "x", "last_ok_bytes": 110 * 10**9}, PRICES, "2026-10", NOW)
        self.assertEqual(line["basis"], "estimate")
        self.assertEqual(line["runRate"], round(100 * 0.00695, 2))


class Credits(unittest.TestCase):
    def test_runway(self):
        self.assertIsNone(zm.runway(5, 0, 0, NOW.date(), 22))
        self.assertEqual(zm.runway(5, 0, 1, NOW.date(), 22), 5)              # $5 at $1 a day
        self.assertEqual(zm.runway(2, 3, 1, NOW.date(), 22), 5)              # included first, then credits
        self.assertEqual(zm.runway(30, 0, 0.5, NOW.date(), 22), 365)         # $15 a month: the 1st refills
        self.assertEqual(zm.runway(30, 0, 1, NOW.date(), 22), 30)            # $30 a month: out on Nov 23

    def test_plan_only_when_no_credits_on_file(self):
        rows = [usage(first=ts(2026, 10, 17, 12), last=ts(2026, 10, 24, 11), output=1_400_000)]   # $14 in 7 days
        c = zm.credits(rows, PRICES, [], None, NOW)
        self.assertEqual(c["name"], "Nous use left")
        self.assertEqual(c["left"], 8.0)                                        # $22 - $14
        self.assertEqual(c["daysLeft"], 4)                                      # $2 a day

    def test_credits_left_after_use_past_included(self):
        rows = [usage(first=ts(2026, 10, 1), last=ts(2026, 10, 20), output=2_000_000),          # $20
                usage(first=ts(2026, 10, 21), last=ts(2026, 10, 24, 11), output=700_000)]       # $7 after
        c = zm.credits(rows, PRICES, [], {"left": 10, "asOf": "2026-10-20T23:00:00-04:00"}, NOW)
        self.assertEqual(c["name"], "Nous use left")
        self.assertEqual(c["left"], 5.0)              # included $22 used up; $10 credits - $5 over
        self.assertIsInstance(c["daysLeft"], int)


class Results(unittest.TestCase):
    def test_follow_ups_sent_this_month(self):
        st = {"events": [{"at": "2026-09-30T10:00:00-04:00", "what": "sent"},
                         {"at": "2026-10-02T10:00:00-04:00", "what": "sent"},
                         {"at": "2026-10-03T10:00:00-04:00", "what": "sent (email not set up)"},
                         {"at": "2026-10-03T11:00:00-04:00", "what": "not approved"}]}
        self.assertEqual(zm.followups_sent(st, "2026-10"), 2)
        self.assertIsNone(zm.followups_sent(None, "2026-10"))

    def test_cut_list_is_unknown(self):
        st = {"events": [{"at": "2026-10-05T10:00:00-04:00", "what": "sent"}] * 400}
        self.assertIsNone(zm.followups_sent(st, "2026-10"))


# ---------------------------------------------------------------- the shape (docs/CONNECTIONS.md)

def connections_examples():
    with open(os.path.join(HERE, "..", "docs", "CONNECTIONS.md")) as fh:
        doc = fh.read()
    section = doc.split("## Val's cost count", 1)[1].split("\n## ", 1)[0]
    full = json.loads(re.search(r"```json\n(.*?)```", section, re.S).group(1))
    bridge = json.loads(re.search(r"for example\s*`(\{.*?\})`", section, re.S).group(1))
    return full, bridge


class Shape(unittest.TestCase):
    def full_count(self):
        rows = [usage(first=ts(2026, 10, 1), last=ts(2026, 10, 24, 11), output=1_500_000)]
        backup = {"last_ok": "2026-10-24T02:30:00-04:00", "last_ok_bytes": 10**8, "stored_bytes": 2 * 10**9}
        fu = {"events": [{"at": "2026-10-20T10:00:00-04:00", "what": "sent"}]}
        return zm.make_count("2026-10", NOW, PRICES, rows, SUBS, backup, fu, None)

    def test_the_docs_examples_pass_the_same_check_as_the_website(self):
        full, bridge = connections_examples()
        self.assertIsNone(zm.check_count(full, ["2026-10"]))
        self.assertIsNone(zm.check_count(bridge, ["2026-10"]))

    def test_vals_count_uses_only_the_documented_fields(self):
        full, _ = connections_examples()
        count = self.full_count()
        self.assertIsNone(zm.check_count(count, ["2026-10"]))
        self.assertLessEqual(set(count), set(full))
        line_keys = set().union(*(s.keys() for s in full["services"]))
        sub_keys = set().union(*(s.keys() for s in full["subscriptions"])) | {"personal"}
        for s in count["services"]:
            self.assertLessEqual(set(s), line_keys, s)
        for s in count["subscriptions"]:
            self.assertLessEqual(set(s), sub_keys, s)
        self.assertLessEqual(set(count["credits"]), set(full["credits"]))
        for lim in count["limits"]:
            self.assertEqual(set(lim), set(full["limits"][0]))
        self.assertLessEqual(set(count["results"]), set(full["results"]))

    def test_vals_count_holds_no_customer_or_key(self):
        raw = json.dumps(self.full_count())
        self.assertEqual(json.loads(raw)["results"], {"followUps": 1})
        for word in ("customer", "phone", "token", "Bearer"):
            self.assertNotIn(word, raw)

    def test_check_refuses_what_the_website_refuses(self):
        good = {"month": "2026-10", "services": [{"id": "a", "name": "A", "billed": 1, "basis": "count"}]}
        bad = [
            ({**good, "month": "2026-9"}, "month must be YYYY-MM."),
            ({**good, "month": "2026-08"}, "month must be 2026-10."),
            ({**good, "services": good["services"] * 2}, 'services has "a" twice.'),
            ({**good, "services": [{"id": "a", "name": "A", "basis": "guess"}]}, "basis must be one of"),
            ({**good, "services": [{"id": "a", "name": "A", "basis": "count", "billed": -1}]}, "from 0 to"),
            ({**good, "services": [{"id": "a", "name": "A", "basis": "count", "kind": None}]}, "kind must be"),
            ({**good, "subscriptions": [{"id": "s", "name": "S"}]}, "cost is needed."),
            ({**good, "subscriptions": [{"id": "s", "name": "S", "cost": 1, "nextRenewal": "soon"}]}, "YYYY-MM-DD"),
            ({**good, "limits": [{"name": "X", "used": None, "limit": 5}]}, "needs used and a limit"),
            ({**good, "credits": {"name": "N", "daysLeft": 5000}}, "from 0 to 3650"),
            ({**good, "results": {"texts": 1.5e7}}, "results.texts"),
        ]
        self.assertIsNone(zm.check_count(good, ["2026-10"]))
        for body, why in bad:
            problem = zm.check_count(body, ["2026-10"])
            self.assertIsNotNone(problem, body)
            self.assertIn(why, problem)

    def test_months_follow_the_website(self):
        self.assertEqual(zm.open_months(NOW), ["2026-10"])
        self.assertEqual(zm.open_months(datetime(2026, 11, 3, tzinfo=TZ)), ["2026-11", "2026-10"])
        self.assertEqual(zm.open_months(datetime(2027, 1, 7, 23, tzinfo=TZ)), ["2027-01", "2026-12"])
        self.assertEqual(zm.open_months(datetime(2026, 11, 8, tzinfo=TZ)), ["2026-11"])


# ---------------------------------------------------------------- posting

class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeWebsite:
    """Stands in for urllib's urlopen: keeps every request, answers like the website's door."""

    def __init__(self, status=200, reason=""):
        self.requests, self.status, self.reason = [], status, reason

    def __call__(self, req, timeout=None):
        body = json.loads(req.data)
        self.requests.append({"url": req.full_url, "method": req.get_method(), "headers": dict(req.header_items()),
                              "body": body, "timeout": timeout})
        if self.status != 200:
            raise urllib.error.HTTPError(req.full_url, self.status, "x", {}, io.BytesIO(self.reason.encode()))
        return FakeResponse(json.dumps({"ok": True, "month": body["month"], "source": "val"}).encode())


class Posting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state = os.path.join(self.tmp, "money-state.json")
        self.inputs = lambda now: {"prices": PRICES, "usage": [usage(output=10**6)], "subs_data": SUBS,
                                   "backup_state": None, "followups_state": None, "credit_file": None}
        self.settings = lambda: ("https://os.example.test/", "val-key")

    def run_at(self, now, site):
        return zm.run_once(now, state_path=self.state, settings=self.settings, inputs_fn=self.inputs, opener=site)

    def test_posts_one_count_with_vals_key(self):
        site = FakeWebsite()
        st = self.run_at(NOW, site)
        self.assertEqual(st["last_error"], "")
        self.assertEqual(len(site.requests), 1)
        r = site.requests[0]
        self.assertEqual((r["method"], r["url"]), ("POST", "https://os.example.test/api/assistant/cost"))
        self.assertEqual(r["headers"]["Authorization"], "Bearer val-key")
        self.assertEqual(r["headers"]["Content-type"], "application/json")
        self.assertEqual(r["body"]["month"], "2026-10")
        self.assertIsNone(zm.check_count(r["body"], ["2026-10"]))

    def test_refusal_is_kept_with_the_websites_reason_and_tried_again_later(self):
        site = FakeWebsite(400, "services[0].basis must be one of receipt, count, estimate.")
        st = self.run_at(NOW, site)
        self.assertIn("400", st["last_error"])
        self.assertIn("basis must be", st["last_error"])
        self.assertNotIn("val-key", json.dumps(st))
        self.assertFalse(zm.due(st, NOW + timedelta(minutes=5)))
        self.assertTrue(zm.due(st, NOW + timedelta(minutes=11)))

    def test_hourly(self):
        st = self.run_at(NOW, FakeWebsite())
        self.assertTrue(zm.due({}, NOW))
        self.assertFalse(zm.due(st, NOW + timedelta(minutes=59)))
        self.assertTrue(zm.due(st, NOW + timedelta(minutes=60)))

    def test_no_settings_sends_nothing(self):
        site = FakeWebsite()
        st = zm.run_once(NOW, state_path=self.state, settings=lambda: ("", ""), inputs_fn=self.inputs, opener=site)
        self.assertEqual(site.requests, [])
        self.assertIn("not set up", st["last_error"])

    def test_first_days_of_a_month_also_close_last_month_once(self):
        site = FakeWebsite()
        nov2 = datetime(2026, 11, 2, 9, tzinfo=TZ)
        st = self.run_at(nov2, site)
        self.assertEqual([r["body"]["month"] for r in site.requests], ["2026-10", "2026-11"])
        closing = site.requests[0]["body"]
        self.assertNotIn("credits", closing)            # last month's final count: lines and results only
        self.assertNotIn("subscriptions", closing)
        self.assertEqual(st["closed_month"], "2026-10")
        self.run_at(nov2 + timedelta(hours=1), site)
        self.assertEqual([r["body"]["month"] for r in site.requests][2:], ["2026-11"])

    def test_count_the_website_would_refuse_is_never_sent(self):
        site = FakeWebsite()
        broken = lambda now: dict(self.inputs(now), prices={"ai": {"nous": {"name": ""}}})
        st = zm.run_once(NOW, state_path=self.state, settings=self.settings, inputs_fn=broken, opener=site)
        self.assertEqual(site.requests, [])
        self.assertIn("would be refused", st["last_error"])


if __name__ == "__main__":
    unittest.main()
