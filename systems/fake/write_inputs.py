"""RFC-0014 B5: write /opt/iproofs/inputs.json from inputs.lock at build time.

Usage: write_inputs.py <inputs.lock> <inputs.json> [<toolchain>=<version> ...]. Standard library
only; runs offline. The Python version is always recorded; an adapter names its other toolchains.
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
toolchains |= dict(arg.split("=", 1) for arg in sys.argv[3:])
out.write_text(json.dumps({"inputs": inputs, "toolchains": toolchains}, sort_keys=True) + "\n")
