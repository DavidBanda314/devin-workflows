"""Observability report: joins Devin API sessions with GitHub issues/PRs into
the remediation funnel: detected -> issue -> session -> PR -> merged.

Writes a terminal report and REPORT.md (also used as a GitHub job summary).
"""

import json
import os
import urllib.request
from datetime import datetime, timezone

from devin_client import list_sessions

TARGET_REPO = os.environ.get("TARGET_REPO", "DavidBanda314/superset")
ISSUE_LABEL = os.environ.get("ISSUE_LABEL", "devin-fix")
AUTOMATION_TAGS = {"devin-audit", "devin-remediation"}


def github_api(path):
    url = f"https://api.github.com{path}"
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_issues():
    return github_api(
        f"/repos/{TARGET_REPO}/issues?labels={ISSUE_LABEL}&state=all&per_page=100"
    )


def get_automation_sessions():
    return [
        s
        for s in list_sessions(limit=200)
        if AUTOMATION_TAGS & set(s.get("tags", [])) and not s.get("is_archived")
    ]


def issue_number_from_tags(tags):
    for t in tags:
        if t.startswith("issue-"):
            try:
                return int(t.split("-", 1)[1])
            except ValueError:
                pass
    return None


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def fmt_ts(ts):
    dt = parse_ts(ts)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "-"


def build_report():
    issues = [i for i in get_issues() if "pull_request" not in i]
    issue_numbers = {i["number"] for i in issues}

    # Scope to sessions tied to an existing issue (deleted issues drop their
    # sessions from the report) plus audit sessions.
    sessions = []
    for s in get_automation_sessions():
        n = issue_number_from_tags(s.get("tags", []))
        if "devin-audit" in s.get("tags", []) or n in issue_numbers:
            sessions.append(s)

    fix_sessions = {}
    audit_sessions = []
    total_acus = 0.0
    for s in sessions:
        total_acus += s.get("acus_consumed") or 0.0
        if "devin-audit" in s.get("tags", []):
            audit_sessions.append(s)
        n = issue_number_from_tags(s.get("tags", []))
        if n in issue_numbers:
            fix_sessions.setdefault(n, s)

    lines = []
    w = lines.append
    now = datetime.now(tz=timezone.utc)
    w("# Devin Remediation Report")
    w("")
    w(f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}  |  Target: `{TARGET_REPO}`")
    w("")

    # Funnel
    n_detected = len(issues)
    n_dispatched = sum(1 for i in issues if i["number"] in fix_sessions)
    prs = {}
    for s in sessions:
        n = issue_number_from_tags(s.get("tags", []))
        if n is None:
            continue
        for pr in s.get("pull_requests") or []:
            if pr.get("pr_url"):
                prs[n] = pr
    n_pr = len([p for p in prs.values() if p])
    n_closed = sum(1 for i in issues if i["state"] == "closed")
    w("## Funnel")
    w("")
    w("| Detected (issues) | Fix sessions | PRs opened | Issues closed |")
    w("|---|---|---|---|")
    w(f"| {n_detected} | {n_dispatched} | {n_pr} | {n_closed} |")
    w("")

    # Per-issue table
    w("## Issue -> Session -> PR")
    w("")
    w("| Issue | State | Session | Status | ACUs | PR | Latency |")
    w("|---|---|---|---|---|---|---|")
    for i in sorted(issues, key=lambda x: x["number"]):
        n = i["number"]
        s = fix_sessions.get(n)
        pr = prs.get(n)
        latency = "-"
        if s:
            t0, t1 = parse_ts(i.get("created_at")), parse_ts(s.get("created_at"))
            if t0 and t1:
                latency = f"{(t1 - t0).total_seconds() / 60:.0f} min"
        w(
            f"| [#{n}]({i['html_url']}) {i['title'][:40]} "
            f"| {i['state']} "
            f"| {(s or {}).get('session_id', '-')[-12:]} "
            f"| {(s or {}).get('status', '-')} "
            f"| {((s or {}).get('acus_consumed') or 0):.1f} "
            f"| {pr['pr_url'] if pr else '-'} "
            f"| {latency} |"
        )
    w("")

    # Session status breakdown
    by_status = {}
    for s in sessions:
        st = s.get("status", "unknown")
        by_status[st] = by_status.get(st, 0) + 1
    w("## Sessions")
    w("")
    w(f"Total automation sessions: **{len(sessions)}** "
      f"(audit: {len(audit_sessions)}, fix: {len(fix_sessions)})  |  "
      f"Total ACUs: **{total_acus:.1f}**")
    w("")
    w("| Status | Count |")
    w("|---|---|")
    for st, c in sorted(by_status.items()):
        w(f"| {st} | {c} |")
    w("")

    # Success signals
    settled = [s for s in fix_sessions.values() if s.get("status") in ("finished", "expired", "blocked", "error")]
    errored = [s for s in fix_sessions.values() if s.get("status") == "error"]
    if fix_sessions:
        rate = n_pr / len(fix_sessions) * 100
        w(f"**PR rate:** {rate:.0f}% of fix sessions produced a PR "
          f"({n_pr}/{len(fix_sessions)}) | errors: {len(errored)} | settled: {len(settled)}")
        if n_pr:
            w("")
            w(f"**Cost:** {total_acus / n_pr:.1f} ACUs per PR")
    return "\n".join(lines)


def main():
    report = build_report()
    print(report)
    out = os.environ.get("REPORT_PATH", "REPORT.md")
    with open(out, "w") as f:
        f.write(report + "\n")
    print(f"\nWrote {out}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(report + "\n")


if __name__ == "__main__":
    main()
