"""Secret-shaped samples, one per RFC-0013 G9 rule, read from fixtures gate G9 skips."""

from pathlib import Path

DIR = Path(__file__).parent / "fixtures/secrets"
RULES = tuple(f"SEC-{i}" for i in range(1, 12))


def sample(rule: str) -> str:
    return (DIR / f"{rule}.txt").read_text().strip()
