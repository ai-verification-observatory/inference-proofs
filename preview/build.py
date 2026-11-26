"""The site of the release after v1.0, as a preview, built in a copy of the tree.

  uv run python preview/build.py OUT [--tree PATH]

`preview/sash/` holds three SASH development sessions that load one setup (slot-1 to slot-3, each
a run directory as its job wrote it) and that setup's record. They are not results: no release
counts them, they ran no control suite, and nothing here is copied into `results/` (RFC-0018 SE-3:
v1.0's slots are filled).

1. Copies the tree (PATH, default this repository; no .git, caches or node_modules) to OUT/tree.
2. There, removes the SASH sessions of results/v1.0/sash and puts the three development sessions
   in their place, one per manifest slot. They share one run id, so each is renamed
   `<stem>-<slot>` (its directory, and `run_id` in run.json and manifest.json; nothing else in a
   record changes). The setup record goes to results/v1.0/sash/_setups/<setup id>/setup.json,
   byte for byte, so the digest the sessions recorded still matches.
3. Builds the board by the further-reply rule (RFC-0018 CO-9: `iproofs release board v1.0
   --cost-rule further-reply`, written to OUT/tree/releases/v1.0/board.json) and the site from it
   into OUT/site, and prints each row's CO-9 figures as the board stores them.

Nothing outside OUT changes. The copy is still labelled v1.0: this is a preview of a rule and of
its figures, not a release. SASH reads "Not passed yet" in it, since these sessions ran no control.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKIP = (".git", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
        ".ruff_cache", ".hypothesis")  # fmt: skip
SASH = "results/v1.0/sash"
FIGURES = ("further_reply_multiple", "further_reply_proving_multiple",
           "further_reply_gpu_seconds", "further_reply_generation_gpu_seconds",
           "further_reply_proving_gpu_seconds", "one_time_gpu_seconds",
           "one_time_mark_replies")  # fmt: skip


def place_sessions(tree: Path) -> list[str]:
    where = tree / SASH
    for d in sorted(where.iterdir()):
        if d.is_dir() and (d / "run.json").is_file():
            shutil.rmtree(d)
    ids = []
    for src in sorted((HERE / "sash").glob("slot-*")):
        run = json.loads((src / "run.json").read_text())
        manifest = json.loads((src / "manifest.json").read_text())
        run_id = re.sub(r"-\d+$", f"-{manifest['session']['slot']}", run["run_id"])
        dst = where / run_id
        shutil.copytree(src, dst)
        for name, doc in (("run.json", run), ("manifest.json", manifest)):
            text = (dst / name).read_text()
            old = json.dumps(doc["run_id"])
            if text.count(f'"run_id": {old}') != 1:
                sys.exit(f"{src / name}: run_id is not written once")
            (dst / name).write_text(text.replace(f'"run_id": {old}', f'"run_id": "{run_id}"'))
        ids.append(run_id)
        setup_id = run["setup"]["setup_id"]
        record = where / "_setups" / setup_id / "setup.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HERE / "sash" / "setup" / "setup.json", record)
    return ids


def summary(board: dict) -> None:  # type: ignore[type-arg]
    print(f"board: cost rule {board.get('cost_rule')}")
    for rung in board["rungs"]:
        for row in rung["rows"]:
            print(f"  {rung['id']} {row['system']}: {len(row['sessions'])} sessions")
            for key in FIGURES:
                q = row.get(key) or {}
                stats = q.get("stats") or {}
                spread = (f" ({stats['min']:.6g} to {stats['max']:.6g}, n = {stats['n']})"
                          if stats.get("min") is not None else "")  # fmt: skip
                print(f"    {key}: {q.get('value')!r} {q.get('unit', '')}{spread}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", type=Path, help="a directory this script may delete and rewrite")
    ap.add_argument("--tree", type=Path, default=HERE.parent,
                    help="the checkout to build from (default: this one)")  # fmt: skip
    a = ap.parse_args()
    out, src = a.out.resolve(), a.tree.resolve()
    if out == src or src in out.parents or out in src.parents:
        sys.exit("OUT must lie outside the tree it copies")
    tree, site = out / "tree", out / "site"
    for d in (tree, site):
        if d.exists():
            shutil.rmtree(d)
    shutil.copytree(src, tree, ignore=shutil.ignore_patterns(*SKIP), symlinks=True)
    print("SASH sessions placed:", ", ".join(place_sessions(tree)))

    def iproofs(*args: str) -> None:  # the tree's own code, run from the copy
        subprocess.run(["uv", "run", "--project", str(src), "iproofs", *args], cwd=tree, check=True)

    iproofs("release", "board", "v1.0", "--cost-rule", "further-reply")
    board = tree / "releases" / "v1.0" / "board.json"
    summary(json.loads(board.read_text()))
    iproofs("site", "build", "--board", str(board), "--out", str(site))
    print(f"site: {site}")


if __name__ == "__main__":
    main()
