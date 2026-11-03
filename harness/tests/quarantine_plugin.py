"""docs/spec/07 §Flaky-test policy: `@pytest.mark.quarantine(issue=<n>)`.

A quarantined test still runs, but its failure does not block: it is reported as xfail with
its issue number (`-ra` lists it) and, in CI, appended to the job summary. There is no retry
(no rerun plugin is allowed; harness/tests/repo/test_quarantine.py checks both rules).
"""

import os

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        marker = item.get_closest_marker("quarantine")
        if marker is not None:
            issue = marker.kwargs.get("issue", marker.args[0] if marker.args else None)
            item.add_marker(pytest.mark.xfail(reason=f"quarantined, issue #{issue}", strict=False))


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    reports = [
        r
        for key in ("xfailed", "xpassed")
        for r in terminalreporter.stats.get(key, [])
        if "quarantined" in str(getattr(r, "wasxfail", ""))
    ]
    if summary and reports:
        with open(summary, "a") as f:
            f.write("Quarantined tests (non-blocking, docs/spec/07 §Flaky-test policy):\n\n")
            for r in reports:
                outcome = "failed" if r.outcome == "skipped" else "passed"
                f.write(f"- `{r.nodeid}` {outcome} ({r.wasxfail})\n")
