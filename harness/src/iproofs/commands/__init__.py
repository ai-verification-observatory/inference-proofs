"""Level 1 command groups (RFC-0018), each registered by its own module.

Every module here defines `register(sub, command)`, which adds its subcommands to the top-level
parser. Handlers import their working modules lazily, as `iproofs.cli` does (INV-ARCH-6).
"""

import argparse
from collections.abc import Callable
from typing import Protocol


class Command(Protocol):
    def __call__(
        self,
        name: str,
        help_text: str,
        parent: "argparse._SubParsersAction[argparse.ArgumentParser] | None" = None,
        full: str | None = None,
    ) -> argparse.ArgumentParser: ...


Register = Callable[["argparse._SubParsersAction[argparse.ArgumentParser]", Command], None]


def registrars() -> list[Register]:
    """The modules' `register` functions, in a fixed order."""
    from iproofs.commands import board, fidelity, level  # noqa: PLC0415

    return [level.register, fidelity.register, board.register]
