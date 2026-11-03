# Known-bad gate fixtures

Each file here must fail one CI gate with one rule id (RFC-0013 §Failure modes of the gates themselves). `iproofs validate` skips this directory when it scans the repository; the tests copy each fixture into a temporary repository and assert the rule.

| Fixture | Gate | Rule |
|---|---|---|
| `G1/ruff_violation.py` | G1 | F401 |
| `G2/run-unknown-workload.json` | G2 | XREF-1 |
| `G2/run-rate-without-scope.json` | G2 | SCHEMA (INV-QTY-3) |
| `G3/not-canonical.json` | G3 | FMT-1 |
| `G4/run.json` | G4 | DER-1 |
| `G5/manifest-bare-float.json` | G5 | LBL-4 |
| `G6/manifest-forbidden-flag.json` | G6 | POL-1 |
| `G6/manifest-nonconforming.json` | G6 | POL-4 |
| `G6/entrypoint-unlisted` | G6 | POL-3 |
| `G7/Dockerfile-unpinned` | G7 | PIN-1, PIN-2, PIN-5 |
| `G7/reference-range.yaml` | G7 | PIN-4 |
| `G8/listed-word.md` | G8 | LANG-1 |
| `G8/emoji.md` | G8 | LANG-2 |
