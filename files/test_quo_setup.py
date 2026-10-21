"""Dry run of the Q5 setup with stand-ins for Vercel, Supabase, Quo, Telegram and
Val's computer. Nothing here reaches the internet."""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quo-bridge"))

import app as bridge_app  # noqa: E402
import quo_setup  # noqa: E402
from bridge import Config  # noqa: E402

BRIDGE = "https://zingas-quo-bridge.vercel.app"


class World:
    def __init__(self, lock_ok=True, existing_supabase=False):
        self.env = {}
        self.deploys = 0
        self.calls = []
        self.lock_ok = lock_ok
        self.existing_supabase = existing_supabase
        self.val_script = None
        self.tg_calls = []
        self.webhooks = [{"id": "WHold", "url": BRIDGE + "/api/quo", "label": "zingas-bridge"}]
        self.deleted = []

    def http(self, method, url, body=None, headers=None, timeout=60):
        self.calls.append((method, url.split("?")[0]))
        path = url.split("?")[0]
        if "api.supabase.com" in url:
            if path.endswith("/v1/projects") and method == "GET":
                return 200, ([{"name": "zingas-quo-bridge", "ref": "abc"}] if self.existing_supabase else [])
            if path.endswith("/organizations"):
                return 200, [{"slug": "zingas", "name": "Zinga's"}]
            if path.endswith("/v1/projects") and method == "POST":
                assert body["region_selection"]["code"] == "us-east-2"
                return 201, {"ref": "abc"}
            if path.endswith("/projects/abc"):
                return 200, {"status": "ACTIVE_HEALTHY"}
            if path.endswith("/database/query"):
                assert "create table if not exists drafts" in body["query"]
                return 201, []
            if path.endswith("/api-keys"):
                return 200, [{"name": "anon", "type": "publishable", "api_key": "sb_publishable_x"},
                             {"name": "default", "type": "secret", "api_key": "sb_secret_x"}]
        if "api.vercel.com" in url:
            assert "teamId=team1" in url or path.endswith("/v2/teams")
            if path.endswith("/v2/teams"):
                return 200, {"teams": [{"id": "team1", "name": "Zinga's"}]}
            if path.endswith("/v9/projects/zingas-quo-bridge"):
                return 404, {}
            if path.endswith("/v11/projects"):
                return 200, {"id": "prj"}
            if path.endswith("/env"):
                assert "upsert=true" in url
                for e in body:
                    assert e["type"] == "sensitive" and e["target"] == ["production"]
                    self.env[e["key"]] = e["value"]
                return 201, {"created": body}
            if path.endswith("/v13/deployments") and method == "POST":
                assert body["target"] == "production"
                assert sorted(f["file"] for f in body["files"]) == sorted(quo_setup.DEPLOY_FILES)
                self.deploys += 1
                return 200, {"id": f"dpl{self.deploys}"}
            if "/v13/deployments/" in path:
                return 200, {"readyState": "READY", "alias": ["zingas-quo-bridge-team.vercel.app",
                                                              "zingas-quo-bridge.vercel.app"]}
        if url.startswith(BRIDGE):
            token = (headers or {}).get("Authorization", "")
            if path.endswith("/api/health"):
                return 200, {}
            if path.endswith("/api/val/updates"):
                return (200 if token == "Bearer " + self.env["VAL_DRAFT_TOKEN"] else 401), {}
            if path.endswith("/api/tick"):
                if not self.lock_ok:
                    return 200, {}
                return (200 if token == "Bearer " + self.env["CRON_SECRET"] else 401), {}
            return 401, {}
        raise AssertionError("unexpected call " + url)

    def quo(self, key, number_id, timeout=15):
        world = self

        class Q:
            def list_numbers(self):
                return [{"id": "PNbiz", "phoneNumber": "+13175550100"}]

            def list_webhooks(self):
                return list(world.webhooks)

            def delete_webhook(self, wid):
                world.deleted.append(wid)

            def create_webhook(self, url, nid):
                assert (url, nid) == (BRIDGE + "/api/quo", "PNbiz")
                return {"id": "WHnew", "key": "whsec_abc"}
        return Q()

    def telegram(self, token, timeout=10):
        world = self

        class T:
            def call(self, method, payload):
                world.tg_calls.append((method, payload))
                if method == "getMe":
                    return {"username": "ValApprovalsBot"}
                if method == "getUpdates":
                    return [{"message": {"chat": {"type": "private"}, "from": {"id": 4242, "first_name": "Gerrit"}}}]
                return True

            def send(self, chat_id, text, buttons=None, force_reply=False):
                world.tg_calls.append(("send", chat_id))
                return 1
        return T()

    def run_on_val(self, cmd, input=None, **kw):
        self.val_script = input
        return mock.Mock(returncode=0, stdout=f"Val pickup program: RUNNING\nquo-bridge answered: 0 new text(s)\n"
                                              f"{self.env['VAL_DRAFT_TOKEN']}\n")

    def run(self):
        stdin = io.StringIO("quo-key\nbot-token\nvercel-token\nsupabase-token\n(317) 555-0999\n")
        out = io.StringIO()
        with mock.patch.object(quo_setup, "http", self.http), \
                mock.patch.object(quo_setup, "QuoClient", self.quo), \
                mock.patch.object(quo_setup, "TelegramClient", self.telegram), \
                mock.patch.object(quo_setup, "ask", lambda prompt: "y"), \
                mock.patch.object(quo_setup.subprocess, "run", self.run_on_val), \
                mock.patch.object(quo_setup.time, "sleep", lambda s: None), \
                mock.patch.object(sys, "stdin", stdin), redirect_stdout(out):
            try:
                quo_setup.main()
                self.error = None
            except quo_setup.Stop as e:
                self.error = str(e)
        self.output = out.getvalue()
        return self


class Q5(unittest.TestCase):
    def test_full_run(self):
        w = World().run()
        self.assertIsNone(w.error, w.output)
        # every setting quo-bridge needs is in Vercel, with the right values
        self.assertTrue(set(bridge_app.REQUIRED) <= set(w.env), set(bridge_app.REQUIRED) - set(w.env))
        cfg = Config.from_env(w.env)
        self.assertEqual((cfg.approver_id, cfg.gerrit_cell, cfg.quo_webhook_secret, cfg.auto_send_enabled),
                         (4242, "+13175550999", "whsec_abc", False))
        self.assertEqual((w.env["QUO_API_KEY"], w.env["APPROVALS_BOT_TOKEN"], w.env["QUO_PHONE_NUMBER_ID"]),
                         ("quo-key", "bot-token", "PNbiz"))
        self.assertEqual((w.env["SUPABASE_URL"], w.env["SUPABASE_SERVICE_KEY"]),
                         ("https://abc.supabase.co", "sb_secret_x"))
        self.assertEqual(len({w.env["VAL_DRAFT_TOKEN"], w.env["CRON_SECRET"], w.env["APPROVALS_WEBHOOK_SECRET"]}), 3)
        # deployed twice: once to get an address, once with Quo's signing key
        self.assertEqual(w.deploys, 2)
        self.assertEqual(w.deleted, ["WHold"])
        hook = [p for m, p in w.tg_calls if m == "setWebhook"][0]
        self.assertEqual((hook["url"], hook["secret_token"]), (BRIDGE + "/api/telegram", w.env["APPROVALS_WEBHOOK_SECRET"]))
        # Val's computer gets only the address and her own code: never the Quo key or bot token
        s = w.val_script
        self.assertIn(w.env["VAL_DRAFT_TOKEN"], s)
        self.assertIn(BRIDGE, s)
        for secret in ("quo-key", "bot-token", "sb_secret_x", "whsec_abc", w.env["CRON_SECRET"],
                       w.env["APPROVALS_WEBHOOK_SECRET"], "vercel-token", "supabase-token"):
            self.assertNotIn(secret, s)
        # nothing secret is printed on screen
        for secret in ("quo-key", "bot-token", "sb_secret_x", "whsec_abc", w.env["VAL_DRAFT_TOKEN"],
                       w.env["CRON_SECRET"], "vercel-token", "supabase-token"):
            self.assertNotIn(secret, w.output)
        self.assertIn("RUNNING", w.output)

    def test_failed_lock_check_stops_before_vals_computer(self):
        w = World(lock_ok=False).run()
        self.assertIn("lock check failed", w.error)
        self.assertIsNone(w.val_script)

    def test_reuses_existing_supabase_project(self):
        w = World(existing_supabase=True).run()
        self.assertIsNone(w.error, w.output)
        self.assertNotIn(("POST", "https://api.supabase.com/v1/projects"), w.calls)

    def test_bad_cell_number_changes_nothing(self):
        w = World()
        stdin = io.StringIO("a\nb\nc\nd\n12345\n")
        with mock.patch.object(quo_setup, "http", w.http), mock.patch.object(sys, "stdin", stdin):
            with self.assertRaises(quo_setup.Stop):
                quo_setup.main()
        self.assertEqual(w.calls, [])


if __name__ == "__main__":
    unittest.main()
