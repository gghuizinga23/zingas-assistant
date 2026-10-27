"""quo_missed_setup: adds call.missed to quo-bridge's Quo call alert, after the new code is online."""
import io
import sys
import unittest
from unittest import mock

import quo_missed_setup as m

HOOKS = [
    {"id": "1", "label": "zingas-bridge-calls", "url": "https://b.vercel.app/api/quo", "createdAt": "2026-10-20",
     "events": ["call.completed"]},
    {"id": "46998", "label": "zingas-bridge-calls", "url": "https://b.vercel.app/api/quo",
     "createdAt": "2026-10-27T00:35", "events": ["call.completed", "call.summary.completed",
                                                 "call.voicemail.completed"]},
    {"id": "46997", "label": "zingas-bridge", "url": "https://b.vercel.app/api/quo", "createdAt": "2026-10-27",
     "events": ["message.received"]},
]


class FakeQuo:
    def __init__(self, hooks):
        self.hooks, self.patches = [dict(h) for h in hooks], []

    def list_webhooks(self):
        return [dict(h) for h in self.hooks]

    def _call(self, method, path, body=None):
        self.patches.append((method, path, body))
        hid = path.rsplit("/", 1)[1]
        for h in self.hooks:
            if h["id"] == hid:
                h["events"] = body["events"]
        return {}


class FakeVercel:
    def __init__(self, order):
        self.order = order

    def call(self, method, path):
        return 200, {}

    def deploy(self):
        self.order.append("deploy")
        return "https://zingas-quo-bridge.vercel.app"


class QuoMissedSetup(unittest.TestCase):
    def run_it(self, hooks, health=200):
        order, quo = [], FakeQuo(hooks)
        real_call = quo._call

        def patch_after_deploy(*a, **k):
            order.append("patch")
            return real_call(*a, **k)
        quo._call = patch_after_deploy
        with mock.patch.object(m.qs, "QuoClient", lambda key, nid: quo), \
                mock.patch.object(m.qs, "Vercel", lambda token: FakeVercel(order)), \
                mock.patch.object(m.qs, "http", lambda method, url: (health, {})), \
                mock.patch.object(sys, "stdin", io.StringIO("vercel-token\nquo-key\n")), \
                mock.patch.object(m.qs, "say", lambda *a: None):
            try:
                m.main()
                stopped = None
            except m.qs.Stop as e:
                stopped = str(e)
        return order, quo, stopped

    def test_newest_calls_alert_gets_call_missed_after_the_code_is_online(self):
        order, quo, stopped = self.run_it(HOOKS)
        self.assertIsNone(stopped)
        self.assertEqual(order, ["deploy", "patch"])
        self.assertEqual(quo.patches, [("PATCH", "/webhooks/46998", {"events": [
            "call.completed", "call.summary.completed", "call.voicemail.completed", "call.missed"]})])

    def test_bad_health_leaves_the_alert_alone(self):
        order, quo, stopped = self.run_it(HOOKS, health=500)
        self.assertIn("was not changed", stopped)
        self.assertEqual(quo.patches, [])

    def test_no_calls_alert_changes_nothing(self):
        order, quo, stopped = self.run_it([HOOKS[2]])
        self.assertIn("no zingas-bridge-calls alert", stopped)
        self.assertEqual(order, [])


if __name__ == "__main__":
    unittest.main()
