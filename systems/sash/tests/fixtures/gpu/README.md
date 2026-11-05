# SASH GPU fixtures

`commit.out.json`, `prove.out.json` and `verify.out.json` are the adapter's own outputs from one job of `sash-l31-8b-c1024` on a rented H100 SXM (hosted execution, RFC-0006), 2026-11-05.

- The image was a development build of `systems/sash/Dockerfile` at adapter commit `9c07cd84ffa6675ed13e507cbf00ba444fd3c6f8`, built in a docker VM, never pushed.
- `commit` ran through the harness.
- The first `prove` stopped on the issues fixed by #283 (crate modes) and #289 (program path). `prove` and `verify` were then called by hand on the same commitment, with the entrypoint of `main` after those fixes, as the hosted runner calls them.
- `prove.out.json` lists the 1,639 part files of the one grid; the parts themselves (42 GB) are not kept.
- Upstream's text lines are kept as the adapter reported them; nothing is edited.

The release-eligible runs come from the pinned image and are under `results/`.
