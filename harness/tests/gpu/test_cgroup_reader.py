"""GPU-host tests of cgroup accounting (RFC-0011 §Cgroup accounting): the slice reader on a
known allocation, and GH-CGROUP-EXACT. Skipped without NVML."""

from pathlib import Path

from iproofs import selftest
from iproofs.measure import CgroupSlice

from .gpu_host import needs_nvml, probe_image

pytestmark = needs_nvml
GIB = 1024**3


def test_slice_reads_known_allocation(tmp_path: Path) -> None:
    """memory.peak and sampled anon both see the probe's 256 MiB (ST-CGROUP)."""
    check = selftest.cgroup(probe_image(), tmp_path)
    assert check.passed, check.detail


def test_cgroup_exact(tmp_path: Path) -> None:
    """GH-CGROUP-EXACT: 1 GiB touched, then exit at once; the final read still sees it."""
    slice_ = CgroupSlice(selftest.run_id(), "probe-exact")
    slice_.start()
    selftest.probe(probe_image(), tmp_path, "alloc", cgroup_parent=slice_.name, mib=1024,
                   hold_s=0)  # fmt: skip
    peak, _ = slice_.finish()
    assert peak >= GIB, f"memory.peak {peak} B"
