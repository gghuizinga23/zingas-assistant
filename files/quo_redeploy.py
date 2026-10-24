"""Zinga's Assistant: put the newest quo-bridge code online. Nothing else changes.

Run by files/quo-redeploy.sh on Gerrit's laptop. One key arrives on stdin (never argv, never saved, never
printed): a Vercel token made for this run (delete it after). It:
  - finds the existing Vercel project "zingas-quo-bridge" (it never makes one),
  - says whether the website link is set (ZINGAS_OS_URL and ZINGAS_OS_TOKEN: names only, never values),
  - uploads the quo-bridge files (quo_setup.DEPLOY_FILES) and waits until Vercel says it is live,
  - asks quo-bridge's /api/health from outside.
It changes no settings and no keys, and texts nobody. Python standard library only.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # run with python3 -I
import quo_setup as qs  # noqa: E402

WEBSITE_LINK = ("ZINGAS_OS_URL", "ZINGAS_OS_TOKEN")


def main():
    lines = sys.stdin.read().splitlines()
    if not lines or not lines[0].strip():
        raise qs.Stop("No Vercel token was pasted. Nothing was changed.")
    vercel = qs.Vercel(lines[0].strip())
    st, _ = vercel.call("GET", f"/v9/projects/{qs.NAME}")
    if st != 200:
        raise qs.Stop(f"Vercel has no project {qs.NAME!r} on this team (HTTP {st}). Nothing was changed.")
    st, env = vercel.call("GET", f"/v9/projects/{qs.NAME}/env")
    names = {e.get("key") for e in (env.get("envs") or [])} if st == 200 else set()
    if all(n in names for n in WEBSITE_LINK):
        qs.say("The website link is set: quo-bridge will send its text count to the Cost tab every hour.")
    else:
        qs.say("The website link (ZINGAS_OS_URL, ZINGAS_OS_TOKEN) is not set, so no text count is sent. "
               "Everything else works as before.")
    qs.say("Putting the newest quo-bridge online (about a minute)...")
    url = vercel.deploy()
    st, _ = qs.http("GET", url + "/api/health")
    if st != 200:
        raise qs.Stop(f"quo-bridge is online but didn't answer its health check (HTTP {st}). Tell Claude.")
    qs.say(f"Done: quo-bridge is live at {url} and answers.")


if __name__ == "__main__":
    try:
        main()
    except qs.Stop as e:
        qs.say(str(e))
        sys.exit(1)
