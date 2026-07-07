"""Trigger A: create a Devin AUDIT session that finds vulnerabilities in the
target repo and files one GitHub Issue per confirmed finding."""

import os

from devin_client import create_session, wait_for_session

TARGET_REPO = os.environ.get("TARGET_REPO", "DavidBanda314/superset")
ISSUE_LABEL = os.environ.get("ISSUE_LABEL", "devin-fix")

AUDIT_PROMPT = f"""You are the detection stage of an automated vulnerability
remediation pipeline for {TARGET_REPO}.

Task:
1. Clone {TARGET_REPO} and audit it for security problems across ALL THREE of
   these categories (cover each category before going deeper on any one):
   a. Dependency CVEs: pinned versions in requirements/ with known CVEs
      (pip-audit / npm audit).
   b. Hardcoded secrets: API keys, tokens, or passwords committed in source
      (grep / secret-scanning patterns).
   c. Unsafe code patterns: SQL built via string interpolation, eval/exec on
      user input, etc. (ruff security rules / manual review).
   Apply your own judgment to filter false positives. Focus on findings that
   are real, high-signal, and fixable — prefer a few solid findings per
   category over exhaustive lists.
2. For EACH confirmed finding, create one GitHub Issue on {TARGET_REPO}
   (use `gh issue create`) with:
   - Title: "[security] <short description>"
   - Label: "{ISSUE_LABEL}" (create the label first if it does not exist)
   - Body containing: **Category** (dependency-cve / hardcoded-secret /
     unsafe-pattern), **Severity**, **File/Line**, **Evidence** (the exact
     vulnerable line or pinned version + CVE id), and **Suggested remediation**.
3. Before filing, check open issues labeled "{ISSUE_LABEL}" and skip
   duplicates.
4. Do NOT fix anything in this session — detection only. A separate pipeline
   stage will remediate each issue.
5. Finish by replying with a summary list of the issue URLs you created.

Do not open any pull requests. Limit yourself to at most 10 issues.
"""


def main():
    session_id, url = create_session(
        prompt=AUDIT_PROMPT,
        title=f"audit: scan {TARGET_REPO} for vulnerabilities",
        tags=["devin-audit", "automated"],
        max_acu_limit=int(os.environ.get("AUDIT_ACU_LIMIT", "20")),
    )
    status, detail = wait_for_session(session_id)
    print(f"Audit session {session_id} status={status} detail={detail}")
    print(f"Follow along: {url}")


if __name__ == "__main__":
    main()
