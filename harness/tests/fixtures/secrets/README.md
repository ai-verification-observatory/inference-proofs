# Secret-scan fixtures

One known-bad sample per RFC-0013 §G9 rule, in `SEC-<n>.txt`. Gate G9 skips this directory when it scans the repository and scans it when it is named explicitly (`uv run iproofs validate harness/tests/fixtures/secrets`). The redactor tests read their samples from here, so no test source holds a secret-shaped literal. The values are invented.
