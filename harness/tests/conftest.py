import os

from hypothesis import settings

# Deterministic property tests in CI (RFC-0013 §G1); select with HYPOTHESIS_PROFILE=ci.
settings.register_profile("ci", max_examples=200, derandomize=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
