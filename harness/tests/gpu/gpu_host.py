"""Shared settings of the GPU-host tests (docs/runbooks/gpu-run.md); never run in CI."""

import os

import pytest

from iproofs.measure import nvml_available

GPU = int(os.environ.get("IPROOFS_GPU", "0"))
PROBE_IMAGE = os.environ.get("IPROOFS_PROBE_IMAGE")  # image ID of the built systems/fake image

needs_nvml = pytest.mark.skipif(not nvml_available(), reason="GPU-host test: needs NVML")


def probe_image() -> str:
    if not PROBE_IMAGE:
        pytest.skip("set IPROOFS_PROBE_IMAGE to the built systems/fake image ID")
    return f"local/fake@{PROBE_IMAGE}"
