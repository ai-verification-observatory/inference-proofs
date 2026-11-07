# Golden files

| File | Inputs |
|---|---|
| `corpus-window-v1-seed0-count3-L8.jsonl` | `corpus_window_v1` over `fixtures/prompts/corpus-a.txt` then `corpus-b.txt` (read as text, joined by one LF), the toy tokenizer `fixtures/prompts/tokenizer.json`, count 3, L 8, seed 0 |
| `index/v0.1.json` | `iproofs release freeze v0.1` over `fixtures/release_tree.py` `build(root)` (5 runs: 3 eligible, 1 dirty, 1 superseded); regenerate with `uv run pytest --update-golden` when the harness version or the index format changes |

A golden file changes only together with a new generator version (RFC-0003 rule 4).
| `site/**` | `iproofs site build` over `fixtures/placeholder_release.py` `build_placeholder(root, extras=True)` after `iproofs release freeze v0.1` (the deployed placeholder release plus its test-only cases: a pending disclosure, an override, a second workload and card, an ineligible, a withdrawn and a failed run, a target, a reply); the files the build writes, not the static assets it copies; regenerate with `uv run pytest --update-golden` |
