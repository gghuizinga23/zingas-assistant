"""quo_sent_setup: which quo-bridge address to keep and which old Quo alerts to remove. Nothing reaches Quo."""
import unittest

import quo_sent_setup as qss


class Plan(unittest.TestCase):
    def test_one_address_and_every_old_alert(self):
        hooks = [{"id": "w1", "label": "zingas-bridge", "url": "https://bridge.example/api/quo"},
                 {"id": "w2", "label": "zingas-bridge-calls", "url": "https://bridge.example/api/quo"},
                 {"id": "w3", "label": "zapier", "url": "https://hooks.zapier.example/x"}]
        url, old = qss.plan(hooks)
        self.assertEqual((url, [w["id"] for w in old]), ("https://bridge.example/api/quo", ["w1", "w2"]))

    def test_two_addresses_or_none_stops_before_any_change(self):
        with self.assertRaises(qss.qs.Stop):
            qss.plan([{"id": "w1", "url": "https://a.example/api/quo"}, {"id": "w2", "url": "https://b.example/api/quo"}])
        with self.assertRaises(qss.qs.Stop):
            qss.plan([])

    def test_the_sent_alert_listens_for_delivered_texts(self):
        self.assertEqual(qss.SENT_EVENTS, ("message.delivered",))


class Leftovers(unittest.TestCase):
    URL = "https://bridge.example/api/quo"

    def hook(self, wid, label, made, url=None):
        return {"id": wid, "label": label, "url": url or self.URL, "createdAt": made}

    def test_the_newest_of_each_stays_and_the_older_ones_go(self):
        hooks = [self.hook("1", "zingas-bridge", "2026-10-22T10:00:00Z"),
                 self.hook("2", "zingas-bridge-calls", "2026-10-22T10:00:01Z"),
                 self.hook("7", "zingas-bridge", "2026-10-27T01:30:00Z"),
                 self.hook("8", "zingas-bridge-calls", "2026-10-27T01:30:01Z"),
                 self.hook("9", "zingas-bridge-sent", "2026-10-27T01:30:02Z"),
                 self.hook("5", "zapier", "2026-10-01T00:00:00Z", url="https://hooks.zapier.example/x")]
        self.assertEqual([w["id"] for w in qss.leftovers(hooks)], ["1", "2"])

    def test_nothing_left_to_remove(self):
        hooks = [self.hook("7", "zingas-bridge", "2026-10-27T01:30:00Z"),
                 self.hook("8", "zingas-bridge-calls", "2026-10-27T01:30:01Z"),
                 self.hook("9", "zingas-bridge-sent", "2026-10-27T01:30:02Z")]
        self.assertEqual(qss.leftovers(hooks), [])

    def test_removes_nothing_unless_all_three_new_alerts_are_there(self):
        hooks = [self.hook("1", "zingas-bridge", "2026-10-22T10:00:00Z"),
                 self.hook("2", "zingas-bridge-calls", "2026-10-22T10:00:01Z")]
        with self.assertRaises(qss.qs.Stop):
            qss.leftovers(hooks)


class DeleteAddress(unittest.TestCase):
    def test_delete_uses_the_2026_version_address(self):
        calls = []

        class Q(qss.qs.clients.QuoClient):
            def _call(self, method, path, body=None, versioned=True):
                calls.append((method, path, versioned))
                return {}

        Q("key", "").delete_webhook("123")
        self.assertEqual(calls, [("DELETE", "/webhooks/123", True)])


if __name__ == "__main__":
    unittest.main()
