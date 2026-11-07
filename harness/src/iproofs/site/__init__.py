"""`iproofs site build`: the static site from the newest frozen release (RFC-0009 §Site).

#320 moves the site to one generator in steps. Today `build` is still the Jinja builder of
`legacy.py`, which writes `site/_build/`; `inputs` reads the release, the claim cards, the
criteria file and `web/_data/facts.json`, and `view.site_view` computes every value the pages
print, for the `web/build.py` renderer that step B of #320 calls from here.
"""

from iproofs.site.legacy import REPOSITORY, build, full, maintainer_rows, number, reply_html

__all__ = ["REPOSITORY", "build", "full", "maintainer_rows", "number", "reply_html"]
