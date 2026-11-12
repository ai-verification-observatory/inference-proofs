"""The wordmark's outlines: INFERENCE and PROOFS in Big Shoulders Display 900, shaped from the
self-hosted font file (fonts/faces.json, latin subset) and written to fonts/wordmark.json, which the
build reads to draw the lockup INFERENCE ⊢ PROOFS (draw/mark.py). Run it again only when the font
file changes; the build stops when the file it names is not the one faces.json lists.

    <python with fonttools and uharfbuzz> -I web/wordmark.py

Each word: its glyphs in order, each with its pen position (kerned, no tracking) and its ink
extent, in units of 1000 per em, y down, baseline at 0. The build adds the tracking.
"""

import io
import json
import pathlib
import sys

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

HERE = pathlib.Path(__file__).resolve().parent
FAMILY, WEIGHT, WORDS = "Big Shoulders Display", 900, ("INFERENCE", "PROOFS")


def main() -> int:
    faces = json.loads((HERE / "fonts" / "faces.json").read_text())["faces"]
    name = next(f["file"] for f in faces if f["fam"] == FAMILY and f["subset"] == "latin")
    font = TTFont(HERE / "fonts" / name)
    if "fvar" in font:
        axes = {a.axisTag for a in font["fvar"].axes}
        font = instantiateVariableFont(font, {"wght": WEIGHT} if "wght" in axes else {})
    font.flavor = None
    buf = io.BytesIO()
    font.save(buf)
    upm = font["head"].unitsPerEm
    s = 1000 / upm
    shaper = hb.Font(hb.Face(buf.getvalue()))
    glyphs, order = font.getGlyphSet(), font.getGlyphOrder()
    out: dict[str, object] = {
        "cap": round(font["OS/2"].sCapHeight * s, 2),
        "file": name,
        "weight": WEIGHT,
        "words": {},
    }
    for word in WORDS:
        b = hb.Buffer()
        b.add_str(word)
        b.guess_segment_properties()
        hb.shape(shaper, b, {"kern": True, "liga": False})
        x, parts = 0.0, []
        for info, pos in zip(b.glyph_infos, b.glyph_positions, strict=True):
            g = order[info.codepoint]
            t = (s, 0, 0, -s, 0, 0)
            pen, box = (
                SVGPathPen(glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip(".")),
                BoundsPen(glyphs),
            )
            glyphs[g].draw(TransformPen(pen, t))
            glyphs[g].draw(TransformPen(box, t))
            x0, y0, x1, y1 = box.bounds
            parts.append({"d": pen.getCommands(), "ink": [round(v, 1) for v in (x0, y0, x1, y1)],
                          "x": round((x + pos.x_offset) * s, 2)})  # fmt: skip
            x += pos.x_advance
        out["words"][word] = parts  # type: ignore[index]
    (HERE / "fonts" / "wordmark.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"fonts/wordmark.json from fonts/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
