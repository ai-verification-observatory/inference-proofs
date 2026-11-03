# fake-broken

This system exists only to be flagged. It is `systems/fake` with one change: `verify` returns `accept`, exit code 0, for every proof, including tampered ones ([RFC-0005 §Reference implementations](../../rfcs/0005-adapter-contract.md#reference-implementations)).

CI runs it through the control suite and asserts that every applicable verifier-side control comes back `accepted`. If the suite ever reports a rejection for this system, the controls or the harness are broken, not the verifier (RFC-0013 §G10). A verifier that accepts everything is a result, so its run records are valid documents; they are never part of a release (`kind: test`).

The entrypoint runs `systems/fake/entrypoint` unchanged with its accept-all switch on, so the prover is the same code as the fake system's. The image is built with `systems/` as its context (`docker build -f systems/fake-broken/Dockerfile systems`).
