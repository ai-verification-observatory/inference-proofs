# Golden files

| File | Inputs |
|---|---|
| `corpus-window-v1-seed0-count3-L8.jsonl` | `corpus_window_v1` over `fixtures/prompts/corpus-a.txt` then `corpus-b.txt` (read as text, joined by one LF), the toy tokenizer `fixtures/prompts/tokenizer.json`, count 3, L 8, seed 0 |
| `index/v0.1.json` | `iproofs release freeze v0.1` over `fixtures/release_tree.py` `build(root)` (5 runs: 3 eligible, 1 dirty, 1 superseded); regenerate with `IPROOFS_UPDATE_GOLDEN=1` when the harness version or the index format changes |

A golden file changes only together with a new generator version (RFC-0003 rule 4).
