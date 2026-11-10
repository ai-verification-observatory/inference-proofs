"""Preview cards: each committed picture was rendered from its committed source, the build writes
that source, and every page names one.

Run from the repository root: uv run pytest web -q
"""

import html
import html.parser
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent


@pytest.fixture(scope="module")
def pages(site):
    b = site.build
    return [b.file_of(p).name for p in ["/", *b.PAGE.values(), b.REF_PAGE, b.CRIT_PAGE]]


def test_pages_print_no_operator_command(pages):
    """A page prints results, never an operator's instruction: no `iproofs` command, whatever a
    stored control note says (a runner before 2026-11-09 wrote "no perturbed commitment; run
    iproofs controls --prepare-perturbed ..." into P1's note; the record keeps it)."""
    for page in [*pages, "release.html", "404.html"]:
        text = html.unescape(re.sub(r"<[^>]+>", " ", (WEB / page).read_text()))
        assert not re.search(r"\biproofs\s+[a-z]", text), page
