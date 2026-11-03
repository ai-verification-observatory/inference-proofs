"""`iproofs site build`: the static site of every frozen release (RFC-0009 §Site).

Inputs are `releases/*/index.json` and `release.yaml`, the claim cards and replies the
release names, `workloads/`, `systems/*/system.yaml` and `rfcs/`. Templates live in
`site/templates/` (Jinja2, autoescape on). Output is plain HTML with no script, written in a
fixed order with no clock, so the same inputs give the same bytes (CLI-4).

Rules held here: S1 the claim card comes before a system's numbers; S2 every number carries
its unit, scope, grade, tier and a link to its JSON Pointer; S3 statistics show mean, sd,
min, max, n and n_failed; S4 four significant digits with the full value in `title`; S5 rows
in alphabetical order, no ranking; S7 superseded and ineligible runs struck through with the
reason; S9 header cells with `scope`, labels as text.
"""

import html
import json
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import jinja2
import yaml
from markupsafe import Markup

REPOSITORY = "https://github.com/ai-verification-observatory/inference-proofs"
PAGES = ("Home", "Release", "System", "Workload", "Methodology")


def number(value: object) -> str:
    """S4: four significant digits for display; the stored value stays in `title`."""
    if value is None:
        return "null"
    if isinstance(value, bool) or not isinstance(value, int | float):
        return str(value)
    return f"{value:#.4g}".rstrip(".") if isinstance(value, float) else str(value)


def full(value: object) -> str:
    return json.dumps(value)


def pointer(*parts: object) -> str:
    """A JSON Pointer from path segments (RFC 6901 escaping)."""
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


def reply_html(text: str) -> Markup:
    """A reply as HTML: everything escaped, then only emphasis, bullet lists and http(s)
    links rendered (RFC-0009 §Right of reply)."""

    def inline(s: str) -> str:
        s = html.escape(s, quote=True)
        s = LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        return re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)

    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.splitlines()
        if lines and all(line.lstrip().startswith(("- ", "* ")) for line in lines):
            items = "".join(f"<li>{inline(line.lstrip()[2:])}</li>" for line in lines)
            out.append(f"<ul>{items}</ul>")
        elif block.strip():
            out.append(f"<p>{inline(' '.join(line.strip() for line in lines))}</p>")
    return Markup("\n".join(out))  # every piece was escaped above


def _environment(templates: Path) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters |= {"number": number, "full": full}
    env.globals |= {"pointer": pointer, "repository": REPOSITORY}
    return env


def _yaml(path: Path) -> dict[str, object]:
    doc = yaml.safe_load(path.read_text("utf-8")) if path.is_file() else None
    return doc if isinstance(doc, dict) else {}


def _rows(index: Mapping[str, object]) -> list[dict[str, object]]:
    """Configurations with their index position, in S5 order."""
    configurations = index["configurations"]
    assert isinstance(configurations, list)
    rows = [{**c, "position": i} for i, c in enumerate(configurations)]
    return sorted(rows, key=lambda c: (str(c["system"]), str(c["workload"]["id"]),
                                       str(c["profile"]), str(c.get("configuration"))))  # fmt: skip


def build(root: Path, out: Path) -> list[Path]:
    """Write the site under `out` (replaced) and return the pages written, sorted."""
    env = _environment(root / "site/templates")
    if out.exists():
        shutil.rmtree(out)
    written: list[Path] = []

    def page(rel: str, template: str, **context: object) -> None:
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        depth = "../" * rel.count("/")
        path.write_text(env.get_template(template).render(root=depth, **context), "utf-8")
        written.append(path)

    releases = sorted(p.parent.name for p in root.glob("releases/*/index.json"))
    kinds = {p.parent.name: _yaml(p) for p in sorted(root.glob("systems/*/system.yaml"))}
    page("index.html", "home.html", releases=releases)
    for release in releases:
        _release(root, out, release, kinds, page)
    return sorted(written)


def _release(root: Path, out: Path, release: str, systems: Mapping[str, Mapping[str, object]],
             page: Callable[..., None]) -> None:  # fmt: skip
    index = json.loads((root / "releases" / release / "index.json").read_text("utf-8"))
    record = _yaml(root / "releases" / release / "release.yaml")
    (out / release).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / "releases" / release / "index.json", out / release / "index.json")
    rows = _rows(index)
    reference = {n for n, s in systems.items() if s.get("kind") == "reference"}
    names = sorted({str(c["system"]) for c in rows})
    workloads = sorted({str(c["workload"]["id"]) for c in rows})  # type: ignore[index]
    reproductions = _reproductions(root, rows)
    common = {"release": release, "record": record, "index": index}
    page(f"{release}/index.html", "release.html", **common, systems=names, workloads=workloads,
         reference=reference, reproductions=reproductions)  # fmt: skip
    rfcs = sorted(p.name for p in root.glob("rfcs/[0-9][0-9][0-9][0-9]-*.md"))
    page(f"{release}/methodology.html", "methodology.html", **common, rfcs=rfcs)
    cards = {(str(c["system"]), str(c["configuration"])): c for c in index["claim_cards"]}
    raw = record.get("replies")
    replies: dict[str, object] = raw if isinstance(raw, dict) else {}
    for name in names:
        mine = [c for c in rows if c["system"] == name]
        mine_workloads = sorted({str(c["workload"]["id"]) for c in mine})  # type: ignore[index]
        card_rows = [cards[k] for k in sorted(cards) if k[0] == name]
        reply_file = replies.get(name)
        reply_path = root / str(reply_file) if reply_file else None
        page(f"{release}/systems/{name}.html", "system.html", **common, system=name,
             is_reference=name in reference,
             cards=[(c, (root / str(c["path"])).read_text("utf-8")) for c in card_rows],
             tables=[(w, [c for c in mine if c["workload"]["id"] == w]) for w in mine_workloads],  # type: ignore[index]
             controls=[c for c in _controls(index) if c["system"] == name],
             reference_rows=[c for c in rows if c["system"] in reference and c["system"] != name
                             and c["workload"]["id"] in mine_workloads],  # type: ignore[index]
             reply=reply_html(reply_path.read_text("utf-8")) if reply_path and reply_path.is_file()
             else None)  # fmt: skip
    for workload in workloads:
        on = [c for c in rows if c["workload"]["id"] == workload]  # type: ignore[index]
        page(f"{release}/workloads/{workload}.html", "workload.html", **common,
             workload=_yaml(root / "workloads" / f"{workload}.yaml"), workload_id=workload,
             rows=[c for c in on if c["system"] not in reference],
             reference_rows=[c for c in on if c["system"] in reference])  # fmt: skip


def _controls(index: Mapping[str, object]) -> list[dict[str, object]]:
    controls = index["controls"]
    assert isinstance(controls, list)
    return sorted(controls, key=lambda c: (str(c["system"]), str(c["workload"]["id"]),
                                           str(c["profile"])))  # fmt: skip


def _reproductions(root: Path, rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Every reproduction record a configuration lists, with its outcome (reproduced or not)."""
    out = []
    for c in rows:
        for rel in c["evidence"]["reproductions"]:  # type: ignore[index]
            doc = json.loads((root / rel).read_text("utf-8"))
            out.append({"system": c["system"], "workload": c["workload"], "profile": c["profile"],
                        "path": rel, "outcome": doc.get("outcome")})  # fmt: skip
    return out
