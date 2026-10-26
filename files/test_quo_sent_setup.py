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


if __name__ == "__main__":
    unittest.main()
