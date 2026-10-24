"""Dry run of files/quo_redeploy.py with a stand-in for Vercel and quo-bridge. Nothing reaches the internet."""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import quo_redeploy  # noqa: E402
import quo_setup  # noqa: E402

BRIDGE = "https://zingas-quo-bridge.vercel.app"


class FakeVercel:
    def __init__(self, project=True, env=("ZINGAS_OS_URL", "ZINGAS_OS_TOKEN")):
        self.project, self.env, self.calls, self.uploaded = project, env, [], None

    def __call__(self, method, url, body=None, headers=None, timeout=60):
        path = url.split("?")[0]
        self.calls.append((method, path))
        if path.endswith("/v2/teams"):
            return 200, {"teams": [{"id": "team1", "name": "Zinga's"}]}
        if path.endswith("/v9/projects/zingas-quo-bridge"):
            return (200, {"id": "prj"}) if self.project else (404, {})
        if path.endswith("/v9/projects/zingas-quo-bridge/env"):
            return 200, {"envs": [{"key": k, "value": "encrypted"} for k in self.env]}
        if path.endswith("/v13/deployments") and method == "POST":
            self.uploaded = sorted(f["file"] for f in body["files"])
            return 200, {"id": "dpl1"}
        if "/v13/deployments/" in path:
            return 200, {"readyState": "READY", "alias": ["zingas-quo-bridge.vercel.app"]}
        if path == BRIDGE + "/api/health":
            return 200, {"ok": True}
        raise AssertionError(f"unexpected call {method} {path}")


def run(fake, stdin="vercel-token\n"):
    out = io.StringIO()
    with mock.patch.object(quo_setup, "http", fake), mock.patch("sys.stdin", io.StringIO(stdin)), \
            redirect_stdout(out):
        try:
            quo_redeploy.main()
            return out.getvalue(), None
        except quo_setup.Stop as e:
            return out.getvalue(), str(e)


class Redeploy(unittest.TestCase):
    def test_uploads_every_file_and_changes_no_setting(self):
        fake = FakeVercel()
        out, err = run(fake)
        self.assertIsNone(err)
        self.assertEqual(fake.uploaded, sorted(quo_setup.DEPLOY_FILES))
        self.assertIn("cost_count.py", fake.uploaded)
        self.assertNotIn(("POST", "https://api.vercel.com/v10/projects/zingas-quo-bridge/env"), fake.calls)
        self.assertFalse(any(m in ("PATCH", "DELETE") for m, _ in fake.calls))
        self.assertIn("text count to the Cost tab every hour", out)
        self.assertIn("is live", out)
        self.assertNotIn("vercel-token", out)

    def test_says_when_the_website_link_is_missing(self):
        out, err = run(FakeVercel(env=("QUO_API_KEY",)))
        self.assertIsNone(err)
        self.assertIn("not set, so no text count is sent", out)

    def test_never_makes_a_new_project(self):
        fake = FakeVercel(project=False)
        _, err = run(fake)
        self.assertIn("Nothing was changed", err)
        self.assertIsNone(fake.uploaded)

    def test_no_token(self):
        _, err = run(FakeVercel(), stdin="\n")
        self.assertIn("No Vercel token", err)


if __name__ == "__main__":
    unittest.main()
