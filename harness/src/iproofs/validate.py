"""Validation checks behind the CI gates (RFC-0013)."""

import dataclasses
import re
from collections.abc import Mapping
from pathlib import Path

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import Binding, ClaimCard, ClaimRef, System, load
from iproofs.schema import SchemaRegistry, parse_tree

NOT_STATED = "not stated"
_COMMIT_IN_PATH = re.compile(r"@[0-9a-f]{40}$")


@dataclasses.dataclass(frozen=True, slots=True)
class Finding:
    """One gate failure, printed in the RFC-0013 §Failure message format."""

    gate: str
    path: str
    rule: str
    message: str
    kind: ErrorKind
    pointer: str = ""
    hint: str = ""

    def line(self) -> str:
        where = f"{self.path}#{self.pointer}" if self.pointer else self.path
        fix = f" (fix: {self.hint})" if self.hint else ""
        return f"{self.gate} {where} {self.rule}: {self.message}{fix}"


# Card fields that state a fact about the system and so need a source (RFC-0002 §Fields).
SOURCED_FIELDS = (
    "relation",
    "relation_formal",
    "security/notion",
    "security/level",
    "security/model",
    "security/setup",
    "zero_knowledge",
    "assumptions",
    "coverage",
    "binding",
    "residual",
    "availability",
    "forbidden_flags",
)


def _not_stated(value: object) -> bool:
    """True when every leaf of `value` says the documentation is silent."""
    if value is None or value in (NOT_STATED, "not_stated"):
        return True
    if isinstance(value, Mapping):
        return all(_not_stated(v) for v in value.values())
    if isinstance(value, list | tuple):
        return all(_not_stated(v) for v in value)
    return False


def _at(tree: Mapping[str, object], path: str) -> object:
    node: object = tree
    for part in path.split("/"):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node


def card_path(root: Path, system: str, configuration: str) -> Path | None:
    """The card for a configuration: `claims/<configuration>.yaml`, else a single `claim.yaml`."""
    multi = root / "systems" / system / "claims" / f"{configuration}.yaml"
    single = root / "systems" / system / "claim.yaml"
    return multi if multi.is_file() else single if single.is_file() else None


def check_claim(path: Path, root: Path, registry: SchemaRegistry) -> list[Finding]:
    """RFC-0002 §Validation, in order: schema, sources, upstream pin, forbidden flags."""
    rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    try:
        card = load(path, registry)
    except IProofsError as e:
        return [Finding("G2", rel, "SCHEMA", e.message, e.kind)]
    if not isinstance(card, ClaimCard):
        return [Finding("G2", rel, "SCHEMA", "not a claim card", ErrorKind.CONFIG)]
    tree = parse_tree(path)  # raw tree: source completeness looks at fields as written
    found: list[Finding] = []
    commit = card.upstream.commit
    for field in SOURCED_FIELDS:  # INV-CLAIM-3
        key = field.replace("/", ".")
        if not _not_stated(_at(tree, field)) and key not in card.sources:
            found.append(
                Finding(
                    "G2",
                    rel,
                    "INV-CLAIM-3",
                    f"{key} has no entry in sources",
                    ErrorKind.INTEGRITY,
                    f"/{field}",
                    "link the upstream documentation at the pinned commit",
                )
            )
    refs = [(f"/sources/{k}", v) for k, v in card.sources.items()]
    gaps = card.quality_gap or ()
    refs += [(f"/quality_gap/{i}/source", g.source) for i, g in enumerate(gaps)]
    if isinstance(card.binding, Binding):
        edges = card.binding.edges or ()
        refs += [(f"/binding/edges/{i}/source", e.source) for i, e in enumerate(edges)]
    if card.relation_formal and card.relation_formal != NOT_STATED:
        refs.append(("/relation_formal", card.relation_formal))
    for pointer, ref in refs:
        if commit not in ref and not _COMMIT_IN_PATH.search(ref):
            found.append(
                Finding(
                    "G2",
                    rel,
                    "INV-CLAIM-3",
                    f"source {ref!r} is not at {commit}",
                    ErrorKind.INTEGRITY,
                    pointer,
                )
            )
    system_file = root / "systems" / card.system / "system.yaml"
    if not system_file.is_file():
        found.append(
            Finding(
                "G2",
                rel,
                "CLAIM-SYSTEM",
                f"systems/{card.system}/system.yaml does not exist",
                ErrorKind.CONFIG,
                "/system",
            )
        )
        return found
    system = load(system_file, registry)
    assert isinstance(system, System)
    if system.upstream is None or system.upstream.commit != commit:
        pinned = system.upstream.commit if system.upstream else None
        found.append(
            Finding(
                "G2",
                rel,
                "CLAIM-PIN",
                f"upstream.commit {commit} != system.yaml {pinned}",
                ErrorKind.INTEGRITY,
                "/upstream/commit",
            )
        )
    extra = sorted(set(card.forbidden_flags or ()) - set(system.forbidden_flags))
    if extra:  # INV-CLAIM-4
        found.append(
            Finding(
                "G2",
                rel,
                "INV-CLAIM-4",
                f"forbidden_flags {extra} are not in system.yaml forbidden_flags",
                ErrorKind.CONFIG,
                "/forbidden_flags",
            )
        )
    return found


def check_run_claim(
    claim: ClaimRef, root: Path, registry: SchemaRegistry, where: str
) -> list[Finding]:
    """A run's manifest `claim` resolves to an existing card at that or a later version."""
    path = card_path(root, claim.system, claim.configuration)
    if path is None:
        return [
            Finding(
                "G2",
                where,
                "CLAIM-REF",
                f"no card for {claim.system}/{claim.configuration}",
                ErrorKind.CONFIG,
                "/claim",
            )
        ]
    card = load(path, registry)
    assert isinstance(card, ClaimCard)
    problems = []
    if card.configuration != claim.configuration:
        problems.append(f"card configuration is {card.configuration!r}")
    if claim.card_version > card.card_version:  # versions only increase (RFC-0002 rule 5)
        problems.append(
            f"card_version {claim.card_version} is newer than the card's {card.card_version}"
        )
    return [Finding("G2", where, "CLAIM-REF", p, ErrorKind.CONFIG, "/claim") for p in problems]
