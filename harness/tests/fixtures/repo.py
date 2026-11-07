"""Git helpers for fixture repositories: fixed identities and dates, so every build of a
fixture tree gives the same commit hashes (release_tree.py, placeholder_release.py)."""

import os
import subprocess
from pathlib import Path

GIT_ENV = {"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
           "GIT_AUTHOR_DATE": "2027-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2027-01-01T00:00:00Z",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}  # fmt: skip


def git(root: Path, *args: str) -> str:
    env = {**os.environ, **GIT_ENV}
    done = subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True, env=env)  # fmt: skip
    return done.stdout.strip()


def commit(root: Path, message: str, *paths: str) -> str:
    git(root, "add", *(paths or ("-A",)))
    git(root, "commit", "-qm", message, "--no-gpg-sign")
    return git(root, "rev-parse", "HEAD")
