# FlashProve GPU fixtures

`commit.out.json`, `prove.out.json` and `verify.out.json` are the adapter's own outputs from one job of `fp-maverick-w1024-b1` on a rented H100 SXM (hosted execution, RFC-0006), 2026-11-05.

- The image was a development build of `systems/flashprove/Dockerfile` at adapter commit `a03797986cd880e5d54508e200194768f105f8fc`, built in a docker VM, never pushed.
- `setup` and `commit` ran through the harness. The fit matched both published digests, and `cp_commit` ended with "complete and can be handed out".
- That job's `prove` stopped on the key-directory mode that #281 fixed. `prove` and `verify` were then called by hand on the same commitment, with the #281 entrypoint, as the hosted runner calls them.
- Upstream's text lines are kept as the adapter reported them; nothing is edited.

The release-eligible runs come from the pinned image and are under `results/`.
