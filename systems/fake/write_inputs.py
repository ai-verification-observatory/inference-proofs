"""RFC-0014 B5: write /opt/iproofs/inputs.json from inputs.lock at build time.

Usage: write_inputs.py <inputs.lock> <inputs.json>. Standard library only; runs offline.
"""

import json
import platform
import sys
from pathlib import Path

lock, out = Path(sys.argv[1]), Path(sys.argv[2])
inputs = []
for line in lock.read_text().splitlines():
    if line.strip() and not line.startswith("#"):
        name, url, digest = line.split("\t")
        inputs.append({"name": name, "url": url, "digest": digest})
toolchains = {"python": platform.python_version()}
out.write_text(json.dumps({"inputs": inputs, "toolchains": toolchains}, sort_keys=True) + "\n")
