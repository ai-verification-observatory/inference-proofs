"""Preview cards: each committed picture was rendered from its committed source, and every page names one.

Run: python3 -m pytest test_cards.py   (or: python3 test_cards.py)
"""

import hashlib
import html.parser
import json
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build

OG = build.OG
RECORD = json.loads((OG / "cards.json").read_text())
PAGES = ["index.html", *build.PAGE.values(), build.REF_PAGE]


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
    m.feed((build.HERE / page).read_text())
    return m.tags


def test_every_source_has_its_picture():
    sources = sorted(p.stem for p in OG.glob("*.html"))
    assert sources == sorted(RECORD) == sorted(p.stem for p in OG.glob("*.png"))
    for card, rec in RECORD.items():
        assert sha(OG / f"{card}.html") == rec["source"], f"og/{card}.html changed: run node og.mjs"
        assert sha(OG / f"{card}.png") == rec["png"], f"og/{card}.png is not the rendered one"


def test_picture_size():
    for card in RECORD:
        png = OG / f"{card}.png"
        want = (
            (build.ICON, build.ICON)
            if card == "icon"
            else (build.CARD_W * build.CARD_SCALE, build.CARD_H * build.CARD_SCALE)
        )
        assert png_size(png) == want, (card, png_size(png))
        assert png.stat().st_size < 1_000_000  # well under the 5 MB the platforms accept


def test_cards_carry_the_draft_label():
    # the states are draft criteria; a picture travels without the page around it, so it says so
    draft = build.html.escape(build.G["legend"]["draft_short"])
    for card in RECORD:
        if card != "icon":
            assert draft in (OG / f"{card}.html").read_text(), card


def test_icon():
    assert (OG / "icon.svg").read_text().startswith("<svg")
    for page in PAGES:
        t = meta(page)
        assert t.get("icon") == "/og/icon.svg", page
        assert t.get("apple-touch-icon", "").startswith("/og/icon.png?v="), page


def test_pages_name_their_card():
    for page in PAGES:
        t = meta(page)
        for k in (
            "og:title",
            "og:description",
            "og:url",
            "og:image",
            "og:image:alt",
            "twitter:image",
        ):
            assert t.get(k), (page, k)
        assert t["twitter:card"] == "summary_large_image"
        assert t["og:image"] == t["twitter:image"]
        assert t["og:url"] == t["canonical"]
        assert t["og:url"].startswith(build.SITE_URL + "/")
        url, v = t["og:image"].split("?v=")
        card = url.rsplit("/", 1)[1].removesuffix(".png")
        assert card in RECORD, (page, t["og:image"])
        assert RECORD[card]["png"].startswith(v), (page, t["og:image"])
        assert t["og:description"] == t["description"]


def test_each_system_has_its_own_card():
    for sid, page in build.PAGE.items():
        assert f"/og/{sid}.png?" in meta(page)["og:image"]


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
