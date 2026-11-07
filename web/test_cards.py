"""Preview cards: each committed picture was rendered from its committed source, the build writes
that source, and every page names one.

Run from the repository root: uv run pytest web -q
"""

import hashlib
import html
import html.parser
import json
import struct
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent
OG = WEB / "og"
RECORD = json.loads((OG / "cards.json").read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_size(path):
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n", path
    return struct.unpack(">II", head[16:24])


class Meta(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        key = a.get("property") or a.get("name") or (a.get("rel") if tag == "link" else None)
        if tag == "link" and key in self.tags and key not in ("canonical",):
            return
        if key:
            self.tags[key] = a.get("content") or a.get("href")


def meta(page):
    m = Meta()
    m.feed((WEB / page).read_text())
    return m.tags


@pytest.fixture(scope="module")
def pages(site):
    b = site.build
    return [b.file_of(p).name for p in ["/", *b.PAGE.values(), b.REF_PAGE, b.CRIT_PAGE]]


def test_every_source_has_its_picture():
    sources = sorted(p.stem for p in OG.glob("*.html"))
    assert sources == sorted(RECORD) == sorted(p.stem for p in OG.glob("*.png"))
    for card, rec in RECORD.items():
        assert sha(OG / f"{card}.html") == rec["source"], f"og/{card}.html changed: run node og.mjs"
        assert sha(OG / f"{card}.png") == rec["png"], f"og/{card}.png is not the rendered one"


def test_sources_are_the_built_ones(site):
    built = sorted(p.name for p in (site.out / "og").glob("*.html"))
    assert built == sorted(p.name for p in OG.glob("*.html"))
    for name in built:
        assert (site.out / "og" / name).read_bytes() == (OG / name).read_bytes(), name


def test_picture_size(site):
    b = site.build
    for card in RECORD:
        png = OG / f"{card}.png"
        want = (b.ICON, b.ICON) if card == "icon" else (b.CARD_W * b.CARD_SCALE, b.CARD_H * b.CARD_SCALE)
        assert png_size(png) == want, (card, png_size(png))
        assert png.stat().st_size < 1_000_000  # well under the 5 MB the platforms accept


def test_system_cards_carry_the_draft_label(site):
    # the states are draft criteria; a picture travels without the page around it, so it says so
    draft = html.escape(site.build.criteria_label()[1])
    for sid in site.build.PAGE:
        assert draft in (OG / f"{sid}.html").read_text(), sid


def test_home_card_holds_nothing_that_changes(site):
    # link previews stay cached in message apps: the home picture names no system and no model
    src = (OG / "home.html").read_text()
    for sid in [*site.view["orders"]["benchmarked"], *site.view["orders"]["reference"]]:
        assert site.view["facts"]["rows"][sid]["name"] not in src, sid
    for name in site.build.MODEL_NAME.values():
        assert name not in src, name
    assert 'class="sl ' not in src  # no system's pie
    assert site.build.card_alt("home").count(":") == 1  # the alt names the properties only


def test_icon(pages):
    assert (OG / "icon.svg").read_text().startswith("<svg")
    for page in pages:
        t = meta(page)
        assert t.get("icon") == "/og/icon.svg", page
        assert t.get("apple-touch-icon", "").startswith("/og/icon.png?v="), page


def test_pages_name_their_card(site, pages):
    for page in pages:
        t = meta(page)
        for k in ("og:title", "og:description", "og:url", "og:image", "og:image:alt", "twitter:image"):
            assert t.get(k), (page, k)
        assert t["twitter:card"] == "summary_large_image"
        assert t["og:image"] == t["twitter:image"]
        assert t["og:url"] == t["canonical"]
        assert t["og:url"].startswith(site.build.SITE_URL + "/")
        url, v = t["og:image"].split("?v=")
        card = url.rsplit("/", 1)[1].removesuffix(".png")
        assert card in RECORD, (page, t["og:image"])
        assert RECORD[card]["png"].startswith(v), (page, t["og:image"])
        assert t["og:description"] == t["description"]


def test_each_system_has_its_own_card(site):
    for sid, path in site.build.PAGE.items():
        assert f"/og/{sid}.png?" in meta(site.build.file_of(path).name)["og:image"]


def test_card_styles_are_css():
    # every card's style holds CSS values only (a Python object printed into it once hid the empty slots)
    for card in RECORD:
        src = (OG / f"{card}.html").read_text()
        for leak in ("re.compile", "<function", "None;"):
            assert leak not in src, (card, leak)


def test_404_is_never_shared():
    t = meta("404.html")
    assert t.get("robots") == "noindex"
    assert "og:image" not in t
    assert "canonical" not in t
