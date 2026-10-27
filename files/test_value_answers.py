"""Price and competitor answers (F6): spot the topic, give Val Gerrit's own words, never a price."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import missed_call as mc
import quo_pickup as qp
import value_answers as va


class TopicTests(unittest.TestCase):
    def test_competitors_and_price(self):
        self.assertEqual(va.topics_in("Budget Blinds came out yesterday"), ["budget_blinds"])
        self.assertEqual(va.topics_in("saw these at home depot for less"), ["big_box"])
        self.assertEqual(va.topics_in("Costco has shades too"), ["costco"])
        self.assertEqual(va.topics_in("found them on blinds.com"), ["online"])
        self.assertEqual(va.topics_in("We got a cheaper quote"), ["other_quote"])
        self.assertEqual(va.topics_in("Honestly it's too expensive for us"), ["price"])
        self.assertEqual(va.topics_in("Lowe's was cheaper, and it's over our budget"), ["price", "big_box"])

    def test_plain_words_bring_up_nothing(self):
        self.assertEqual(va.topics_in("Thanks! Tuesday works for the install"), [])
        self.assertEqual(va.topics_in("Can you send the fabric photos?"), [])


class FileTests(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp()

    def test_save_and_load_keep_gerrits_words(self):
        va.save({"budget_blinds": "They send a franchise guy.\nWe install ourselves.", "general": "Lifetime warranty."},
                 self.vault)
        got = va.load(self.vault)
        self.assertEqual(got["budget_blinds"], "They send a franchise guy.\nWe install ourselves.")
        self.assertEqual(got["general"], "Lifetime warranty.")
        self.assertEqual(oct(os.stat(va.path(self.vault)).st_mode & 0o777), "0o600")

    def test_answers_with_a_number_are_refused(self):
        self.assertIsNotNone(va.check_answer("We are $200 cheaper"))
        self.assertIsNotNone(va.check_answer("We beat them by 10%"))
        self.assertIsNotNone(va.check_answer(""))
        self.assertIsNone(va.check_answer("We measure and install it ourselves, no subcontractors."))

    def test_block_uses_the_fitting_answer_and_the_general_one(self):
        va.save({"budget_blinds": "BB answer", "costco": "Costco answer", "general": "Main points"}, self.vault)
        block = va.prompt_block("Budget Blinds quoted us", vault=self.vault)
        self.assertIn("BB answer", block)
        self.assertIn("Main points", block)
        self.assertNotIn("Costco answer", block)
        self.assertIn("Never a price", block)
        self.assertIn("Never say a bad word", block)

    def test_block_without_answers_says_gerrit_goes_over_it(self):
        block = va.prompt_block("too expensive", vault=self.vault)
        self.assertIn("not saved yet", block)
        self.assertIn("Gerrit will go over it", block)

    def test_no_topic_no_block(self):
        self.assertEqual(va.prompt_block("See you Tuesday", vault=self.vault), "")

    def test_command_set_show_remove(self):
        with mock.patch("sys.stdin", io.StringIO("We install it ourselves.")):
            self.assertEqual(_run(["set", "costco", "--text-file", "-"], self.vault), 0)
        self.assertEqual(va.load(self.vault)["costco"], "We install it ourselves.")
        with mock.patch("sys.stdin", io.StringIO("Only $99!")):
            self.assertEqual(_run(["set", "price", "--text-file", "-"], self.vault), 1)
        self.assertNotIn("price", va.load(self.vault))
        self.assertEqual(_run(["remove", "costco"], self.vault), 0)
        self.assertEqual(va.load(self.vault), {})


def _run(argv, vault):
    with mock.patch.object(va, "VAULT", vault), redirect_stdout(io.StringIO()):
        return va.main(argv)


class PromptTests(unittest.TestCase):
    def test_text_reply_prompt_carries_the_block(self):
        t = {"phone": "+13175550101", "text": "Home Depot was cheaper", "thread": []}
        p = qp.build_prompt(t, None, vault=tempfile.mkdtemp(), answers="## Price or a competitor came up (X)")
        self.assertIn("## Price or a competitor came up (X)", p)
        self.assertNotIn("\n\n\n\n", qp.build_prompt(t, None, vault=tempfile.mkdtemp()))

    def test_missed_call_prompt_carries_the_block(self):
        p = mc.call_prompt({"kind": "voicemail", "text": "costco"}, "Pat", "", answers="## Price or a competitor")
        self.assertIn("## Price or a competitor", p)

    def test_pickup_block_reads_customer_words(self):
        with mock.patch.object(qp, "VAULT", tempfile.mkdtemp()):
            self.assertIn("Budget Blinds", qp.answers_block("ok", "Budget Blinds came by"))
            self.assertEqual(qp.answers_block("thanks!"), "")


if __name__ == "__main__":
    unittest.main()
