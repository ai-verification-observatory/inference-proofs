# Security policy

This file covers two kinds of report: vulnerabilities in this project's own code, and a verifier of a measured system that accepts a tampered input. Neither belongs in a public issue or pull request.

## Reporting channel

Report privately through the hosting platform's private vulnerability reporting for this repository ("Report a vulnerability" on the Security tab). This resolves [RFC-0001](rfcs/0001-process-and-governance.md#open-questions) Q3 with its default.

## Vulnerabilities in this project

In scope: the harness (`harness/`), the fake systems (`systems/fake`, `systems/fake-broken`), the CI workflows and the site generator. Examples include a container escape path, a path traversal through adapter output, a secret or host identifier written into a run directory, or a validation gate that can be bypassed.

- Maintainers acknowledge a report within 7 days. This is a target, not a guarantee.
- Maintainers publish a fix and an advisory.
- A vulnerability that could have affected published numbers is listed in the next release report under "what failed", with the affected runs ([docs/spec/06-security.md §Harness vulnerabilities](docs/spec/06-security.md#harness-vulnerabilities)).

Vulnerabilities in a measured prover belong to its upstream project and its own security policy.

## A verifier that accepts a tampered input

A negative control whose expected outcomes exclude `accept`, accepted on a real system, is a possible soundness or adapter defect ([RFC-0008 §Disclosure](rfcs/0008-negative-controls.md#disclosure), [docs/spec/06-security.md §Accepted controls](docs/spec/06-security.md#accepted-controls-a6)).

1. The runner does not open a public pull request with that run. They report privately to the system's maintainers through the channel in the system's security policy, or, when none is published, through the maintainers listed in its `system.yaml`. They also report to the benchmark maintainers through the channel above.
2. The embargo follows the system's own policy. If it has none, the embargo lasts 90 days from the report or until the upstream publishes a fix or advisory, whichever is earlier.
3. During the embargo, `controls.json` carries `disclosure_pending: true`, and a release that contains the run says a disclosure is pending, without details.
4. After the embargo the run is published in full, with the outcome printed in the row.
5. The run is not discarded, and the result is not softened.

Before reporting against a system, the runner checks the adapter. A fault in this repository's verdict mapping is fixed here and the run is redone; it is not a finding against the system.
