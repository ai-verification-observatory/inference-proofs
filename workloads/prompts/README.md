# Prompt corpus

`corpus.yaml` lists the texts every v0.1 workload draws its prompts from (RFC-0003 §Prompt corpus). The generator `corpus-window/1` takes windows at seeded offsets, so a prompt can come from any of them.

## The texts

| Id | Title | Author | First published | Gutenberg release |
|---|---|---|---|---|
| `gutenberg-1342` | Pride and Prejudice | Jane Austen | 1813 | eBook #1342 |
| `gutenberg-2701` | Moby Dick; Or, The Whale | Herman Melville | 1851 | eBook #2701 |
| `gutenberg-84` | Frankenstein; or, The Modern Prometheus | Mary Wollstonecraft Shelley | 1818 | eBook #84 |
| `gutenberg-11` | Alice's Adventures in Wonderland | Lewis Carroll | 1865 | eBook #11 |
| `gutenberg-1661` | The Adventures of Sherlock Holmes | Arthur Conan Doyle | 1892 | eBook #1661 |
| `gutenberg-98` | A Tale of Two Cities | Charles Dickens | 1859 | eBook #98 |
| `gutenberg-74` | The Adventures of Tom Sawyer | Mark Twain | 1876 | eBook #74 |
| `gutenberg-345` | Dracula | Bram Stoker | 1897 | eBook #345 |

## Why these

- **Licence basis.** Each work was first published before 1929, so it is in the public domain in the United States; Project Gutenberg distributes each as a US public-domain eBook (the "public domain in the USA" statement in each file's header). This repository commits only the URLs and hashes, never the texts.
- **Size.** Together they hold 5,411,405 bytes of English prose (the sum of the `bytes` fields), far more than one prompt of 4,096 tokens under any v0.1 tokenizer. RFC-0003's generator draws windows at random offsets, so the corpus only has to exceed one prompt; it is sized for variety of style and vocabulary (novels, short stories, dialogue, archaic and modern spelling), not for prompt count.
- **Stability.** The URLs are Gutenberg's plain-text cache paths by eBook number. Every hash was taken on 2026-11-03 and matched a second, fresh download the same day. If Gutenberg republishes a file, its bytes change: `iproofs prompts build` then fails with `integrity` and the corpus gets a new version through a pull request (the corpus digest is part of every workload's identity).

## Corpus digest

`sha256:cedd5c414e7c70b99348140c4ddfde8754446c3d3085f77d5d29a4e7324f639a`: sha256 over the lines `<id>\t<sha256>\n` sorted by id bytes (RFC-0003), computed with `iproofs.provenance.corpus_digest`. Every v0.1 workload's `prompts.corpus_digest` names it (#49).
