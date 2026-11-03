"""A deterministic synthetic results tree for the tooling budgets (docs/spec/08 §Profiling plan).

`generate(root, runs=1000)` writes `results/v0.1/fake/<run-id>/{run,manifest}.json` from the
`run/1` and `manifest/1` valid examples, one directory per run id, so `iproofs validate` and
`iproofs derive --check` have a tree of realistic size. The only variation is the run id and
its date, drawn from a fixed seed, so two generations are byte-identical.
"""

import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_ID = "2026-11-20-fake-fake-tiny-ci-ci-cpu-1"
SEED = 20261103


def generate(root: Path, runs: int = 1000, seed: int = SEED) -> list[Path]:
    run = (ROOT / "schema/run/examples/valid/fake-success.json").read_text()
    manifest = (ROOT / "schema/manifest/examples/valid/fake-success.json").read_text()
    rng = random.Random(seed)
    out = []
    for n in range(1, runs + 1):
        day = 1 + rng.randrange(28)
        run_id = f"2026-11-{day:02d}-fake-fake-tiny-ci-ci-cpu-{n}"
        d = root / "results/v0.1/fake" / run_id
        d.mkdir(parents=True)
        (d / "run.json").write_text(run.replace(TEMPLATE_ID, run_id))
        (d / "manifest.json").write_text(manifest.replace(TEMPLATE_ID, run_id))
        out.append(d)
    return out
