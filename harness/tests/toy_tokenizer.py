"""Character tokenizer read from a stored vocabulary, standing in for `tokenizers` in CI."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToyEncoding:
    ids: Sequence[int]


class ToyTokenizer:
    def __init__(self, path: Path) -> None:
        self.vocab: dict[str, int] = json.loads(path.read_text())["vocab"]

    def encode(self, sequence: str, *, add_special_tokens: bool) -> ToyEncoding:
        assert add_special_tokens is False  # the generator never inserts special tokens
        return ToyEncoding([self.vocab[c] for c in sequence])


class RangeTokenizer:
    """Maps a text of length N to ids 0..N-1, so a prompt's first id is its offset."""

    def encode(self, sequence: str, *, add_special_tokens: bool) -> ToyEncoding:
        return ToyEncoding(list(range(len(sequence))))
