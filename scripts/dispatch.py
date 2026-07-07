"""Trigger B: create a Devin FIX session for one GitHub Issue.

Invoked by the `on: issues` workflow in the target repo whenever an issue is
opened with (or labeled with) the remediation label. Reads the issue payload
from env vars, creates a Devin session to remediate it, and comments the
session URL back on the issue.
"""

import json
import os
import subprocess

from devin_client import create_session, wait_for_session

TARGET_REPO = os.environ.get("TARGET_REPO", "DavidBanda314/superset")
ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]
ISSUE_TITLE = os.environ.get("ISSUE_TITLE", "")
ISSUE_BODY = os.environ.get("ISSUE_BODY", "")
ISSUE_URL = os.environ.get("ISSUE_URL", f"https://github.com/{TARGET_REPO}/issues/{ISSUE_NUMBER}")


def build_prompt():
    return f"""You are the remediation stage of an automated vulnerability
remediation pipeline for {TARGET_REPO}.

Fix the security finding described in this GitHub issue:

Issue #{ISSUE_NUMBER}: {ISSUE_TITLE}
{ISSUE_URL}

Issue body:
{ISSUE_BODY}

Instructions:
1. Clone {TARGET_REPO} and validate the finding first (confirm the vulnerable
   code/dependency actually exists as described). If it is a false positive,
   comment your analysis on the issue and stop.
2. Apply the minimal, correct remediation (e.g. bump the pinned dependency to
   the fixed version, move the hardcoded secret to an environment variable,
   replace the unsafe pattern with a safe equivalent).
3. Verify the change (lint the touched files; run any quick relevant checks).
4. Open a pull request against {TARGET_REPO}'s default branch. The PR
   description MUST include the line "Fixes #{ISSUE_NUMBER}" so the issue
   auto-closes on merge, and must explain the vulnerability and the fix.
5. Comment on issue #{ISSUE_NUMBER} with a link to the PR.

Keep the diff minimal and scoped to this one finding only.
"""


def comment_on_issue(text):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("No GITHUB_TOKEN; skipping issue comment")
        return
    subprocess.run(
        ["gh", "issue", "comment", ISSUE_NUMBER, "-R", TARGET_REPO, "--body", text],
        check=False,
        env={**os.environ, "GH_TOKEN": token},
    )


def main():
    session_id, url = create_session(
        prompt=build_prompt(),
        title=f"fix: remediate issue #{ISSUE_NUMBER} — {ISSUE_TITLE[:60]}",
        tags=["devin-remediation", f"issue-{ISSUE_NUMBER}", "automated"],
        max_acu_limit=int(os.environ.get("FIX_ACU_LIMIT", "15")),
    )
    comment_on_issue(
        f"🤖 Devin remediation session started for this issue: {url}\n\n"
        f"Session ID: `{session_id}` — a PR referencing this issue will follow."
    )
    status, detail = wait_for_session(session_id)
    print(f"Fix session {session_id} status={status} detail={detail}")

    # Machine-readable line for log scraping / observability
    print(json.dumps({
        "event": "fix_session_dispatched",
        "issue": int(ISSUE_NUMBER),
        "session_id": session_id,
        "session_url": url,
        "status": status,
    }))


if __name__ == "__main__":
    main()
