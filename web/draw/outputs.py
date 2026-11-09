"""The files written beside the pages: search.json, vercel.json (with the inline script's hash),
the preview-card sources and icon in og/, the @font-face block between the markers in words.css
(stopping the build when the markers are missing) and the contrast table in README.md.
"""

import base64
import hashlib
import re

from . import state as S
from .chrome import (
    CARD_H,
    CARD_W,
    CRIT_PAGE,
    HEAD_SCRIPT,
    REF_PAGE,
    RELEASE_PAGE,
    font_faces,
    ref_label,
)
from .hexagon import key_mini, mark_svg, pie_svg
from .inks import GHOST, GROUND, MUTED, PAPER, UNSTATED, VIOLET, ratio
from .overview import board_configs, fig_href, kind_words, nb_meta, nb_models
from .pages import SIDE
from .plates import COLS, HEAD, MORE, PER_GBIT_COLS, first_config, glyph, name_of, upstream
from .words import FAMILY_WORD, STATE_CLS, curly, e

# ------------------------------------------------------------------ search
# search.json, the local index the header's search reads (words.js; nothing leaves the browser).
# Systems, references, properties and the pages. Each entry: its name, where it leads, its kind,
# the group words.js lists it under and the group's tier (benchmarked first, not benchmarked last:
# the order says what kind of entry it is, never how good a system is), a line of context, its pie
# and the words it is found by; the phrases among them a result shows in place of its line of
# context when it was found by one (`found`), and a Figures section's figures, each with the
# plate it leads to (`figures`); a section's `context`, its system's name and models, which find it
# only beside a word of its own ("sash tamper"). TERMS adds the words people search with for a
# family of systems.
# Only words true of every system in the family: how a system proves (STARK, SNARK, sumcheck...) comes
# from its own stated technique, never from its family (AGENTS.md rule 9).
TERMS = {
    "proved": "zk proof cryptographic",
    "attested": "tee enclave hardware attestation confidential",
    "re-executed": "rerun re-execution recompute optimistic dispute",
    "fingerprinted": "fingerprint",
}
# words for what the facts' code field says about a system's source
CODE_TERMS = {"no_public_code": "closed source"}
TIER = {"system": 0, "section": 1, "reference": 2, "property": 3, "page": 4, "unbenchmarked": 5}
GROUP = {"system": "Benchmarked", "reference": "References", "property": "Properties",
         "page": "Pages", "unbenchmarked": "Not benchmarked"}  # fmt: skip
# a system page's sections, each found by what it holds; listed under the system's name
SECTIONS = (
    ("Figures", "figures", "figures numbers measured spread runs"),
    ("Tamper tests", "tamper", "tamper tests controls negative accepted rejected"),
    ("How we read it", "how-we-read", "how we read it quotes sources read"),
    ("Claim card in full", "card-{configuration}", "claim card residual quality gap"),
)
# what a not-benchmarked system's facts say is absent: shown on its card, never searched by
ABSENT = re.compile(r"^(?:no |not named|model not named)", re.I)
ABSENT_NOTES = re.compile(
    r"\s*\((?:model id as given|size not stated)\)|,\s*(?:size not stated|none named)"
)


def model_terms(models):
    """A system's models as phrases to search by: each name, its notes and every phrase that says
    a model is absent ("not named", "no LLM named", "size not stated") left out."""
    out = []
    for given in models:
        for part in given.split(";"):
            said = ABSENT_NOTES.sub("", part).strip()
            if said and not ABSENT.match(said):
                out.append(curly(said))
    return out


def search_entries():
    out = []

    def add(kind, name, url, meta, pie, found=(), fam="", **more):
        """One entry. Its context line is searched by too, except a not-benchmarked system's,
        which may show an absence ("Model not named"); its terms say what it does name: the
        phrases it shows when found by one (`found`), its figures' names (`figures`) and
        `terms`, words it is found by and never shows; `group`, where not its kind's; a
        section's `context`."""
        group, terms, figures, context = (more.get(k) for k in ("group", "terms", "figures",
                                                                "context"))  # fmt: skip
        found = [x for x in dict.fromkeys(found) if x]
        shown = "" if kind == "unbenchmarked" else meta
        said = [*found, *(f["name"] for f in figures or [])]
        words_ = " ".join([name, shown, *said, terms or "", TERMS.get(fam, ""), fam])
        entry = {
            "kind": kind,
            "tier": TIER[kind],
            "group": group or GROUP[kind],
            "name": name,
            "url": url,
            "meta": meta,
            "pie": pie,
            "terms": " ".join(words_.lower().split()),
            "found": found,
        }
        if figures:
            entry["figures"] = figures
        if context:
            entry["context"] = " ".join(context.lower().split())
        out.append(entry)

    def ran(sid):
        """What a system's or reference's configurations ran, phrase by phrase: workloads,
        models, the precision proved with its words ("W8A8 (8-bit weights and activations)"),
        GPUs, profiles, engines."""
        out_ = []
        for c in (c for c in S.CONFIGS if c["system"] == sid):
            sv = c.get("serving") or {}
            digest = c["workload"]["model"]["digest"]
            # the precision a prover proved; serving names the precision it served (below)
            proved = (
                (c["workload"]["precision"].get("proved") or "") if c["kind"] == "prover" else ""
            )
            said = S.V["facts"]["models"].get(digest, {}).get("precision_words", {}).get(proved)
            out_ += [c["workload"]["id"], S.MODEL_NAME[digest],
                     f"{proved} ({said})" if proved and said else proved,
                     c["gpu"]["model"] or "", c["gpu"]["short"] or "", c["profile"],
                     sv.get("engine") or "", sv.get("precision") or ""]  # fmt: skip
        return list(dict.fromkeys(x for x in out_ if x))

    board = {c["system"]: c for c in board_configs()}

    for sid in S.V["orders"]["benchmarked"]:
        cfg = first_config(sid)
        fam = FAMILY_WORD[S.CRIT["rows"][sid]["family"]]
        kind_title = f"{fam}: {S.V['facts']['rows'][sid]['technique']}"
        add(
            "system",
            name_of(sid),
            S.PAGE[sid],
            S.MODEL_NAME[cfg["workload"]["model"]["digest"]],
            pie_svg(glyph(sid)["states"], 28),
            [kind_title, upstream(cfg)["repo"], *ran(sid)],
            fam.lower(),
        )
    for sid in S.V["orders"]["benchmarked"]:
        cfg = first_config(sid)
        # each figure leads to its plate in the setup the overview row shows; the more-numbers
        # rows to the figures
        figures = [
            {"name": HEAD[c], "url": fig_href(board[sid], c)} for c in (*COLS, *PER_GBIT_COLS)
        ]
        figures += [{"name": label, "url": f"{S.PAGE[sid]}#figures"} for _, label in MORE]
        # a section is found by its system's name and models beside a word of its own ("sash
        # tamper"), never by them alone: the system's entry is that match
        whose = " ".join(
            [
                name_of(sid),
                *dict.fromkeys(
                    S.MODEL_NAME[c["workload"]["model"]["digest"]]
                    for c in S.CONFIGS
                    if c["system"] == sid
                ),
            ]
        )
        for title, anchor, terms in SECTIONS:
            add("section", title, f"{S.PAGE[sid]}#{anchor.format(configuration=cfg['configuration'])}",
                "", "", group=name_of(sid), terms=terms, context=whose,
                figures=figures if anchor == "figures" else None)  # fmt: skip
    for gid in S.V["orders"]["reference"]:
        add(
            "reference",
            name_of(gid),
            f"{REF_PAGE}#{gid}",
            kind_words(gid),
            pie_svg(glyph(gid)["states"], 28),
            ran(gid),
            terms="reference references baseline",
        )
    for rid in S.V["orders"]["not_benchmarked"]:
        r = S.V["facts"]["rows"][rid]
        fam = FAMILY_WORD[S.CRIT["rows"][rid]["family"]]
        add(
            "unbenchmarked",
            r["name"],
            f"/#nb-{rid}",
            nb_models(r),
            pie_svg(glyph(rid)["states"], 28),
            # status, models, source and stated technique, never an absence ("not named", "no
            # repository", "no public code"); not the people behind it
            [
                "" if r["status"]["state"] == "no_repository" else nb_meta(rid),
                *model_terms(r["models"]),
                CODE_TERMS.get(r.get("code"), ""),
                r.get("technique") or "",
            ],
            fam.lower(),
        )
    for i, p in enumerate(S.PROPS):
        add("property", p["name"], f"{CRIT_PAGE}#{p['id']}", p["question"], key_mini(i + 1, 28))
    rel = S.V["release"]
    refs = S.V["orders"]["reference"]
    # while /reference holds one reference, its entry is the page's: one entry, not two
    pages = [(ref_label(), REF_PAGE, ", ".join(name_of(g) for g in refs),
              "reference baseline serving")] if len(refs) > 1 else []  # fmt: skip
    pages += [("Criteria", CRIT_PAGE, "What each state means for each property",
              "criteria states rules yes partly no not stated"),
             (f"Release {rel['id']}", RELEASE_PAGE, "Its runs, claim cards and reference file",
              "release runs records index overhead cost price")]  # fmt: skip
    for name, url, meta, terms in pages:
        add("page", name, url, meta, mark_svg(28, cls="pie-svg lm"), terms=terms)
    return out


# ------------------------------------------------------------------ vercel.json, from the build
# Headers, redirects and cache rules depend on the build's own output (the inline script's hash,
# the first system page), so the build writes the whole file. Canonical JSON (iproofs fmt).
def vercel_json():
    script = hashlib.sha256(HEAD_SCRIPT.encode()).digest()

    csp = "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' 'sha256-{base64.b64encode(script).decode()}'",
            "style-src 'self'",
            "img-src 'self'",
            "font-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
            "frame-ancestors 'none'",
        ]
    )
    forever = [{"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}]
    first = S.PAGE[S.V["orders"]["benchmarked"][0]]
    return {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "buildCommand": "rm -rf public && mkdir -p public/og public/fonts && cp *.html words.css words.js search.json public/ && cp og/*.png og/*.svg public/og/ && cp fonts/*.woff2 public/fonts/",
        "cleanUrls": True,
        "trailingSlash": False,
        "framework": None,
        "ignoreCommand": "git diff --quiet HEAD^ HEAD -- .",
        "outputDirectory": "public",
        "redirects": [
            {"source": "/system", "destination": first, "permanent": True},
            {"source": "/system.html", "destination": first, "permanent": True},
            # clients that ask for /favicon.ico get the PNG icon
            {"source": "/favicon.ico", "destination": "/og/icon-32.png", "permanent": False},
        ],
        "headers": [
            {
                "source": "/(.*)",
                "headers": [
                    # noindex: the site is not announced (README)
                    {"key": "X-Robots-Tag", "value": "noindex"},
                    {"key": "X-Content-Type-Options", "value": "nosniff"},
                    {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"},
                    {"key": "Content-Security-Policy", "value": csp},
                    {"key": "X-Frame-Options", "value": "DENY"},
                    {
                        "key": "Permissions-Policy",
                        "value": "camera=(), microphone=(), geolocation=()",
                    },
                ],
            },
            # versioned by ?v=<hash> (words.css, words.js, the pictures) or by the file name (fonts)
            {"source": "/(words\\.css|words\\.js|search\\.json)", "headers": forever},
            {"source": "/og/(.*)\\.png", "headers": forever},
            {"source": "/fonts/(.*)", "headers": forever},
        ],
    }


# ------------------------------------------------------------------ preview card sources
# og/<card>.html for og.mjs to render, and the icon (the share tags that name them: chrome.py).


def card_css():
    return f"""
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{CARD_W}px;height:{CARD_H}px;overflow:hidden;background:{GROUND};color:{PAPER};-webkit-font-smoothing:antialiased}}
.mono{{font-family:"IBM Plex Mono",monospace}}
.disp{{font-family:"Archivo",sans-serif;font-stretch:66%;font-weight:900}}
.sl.yes{{fill:{S.INK["yes"]}}}.sl.partly{{fill:{S.INK["partly"]}}}.sl.no{{fill:{S.INK["no"]}}}
.sl.unstated{{fill:{GHOST};stroke:{UNSTATED};stroke-width:2px;vector-effect:non-scaling-stroke;stroke-linejoin:round}}
.pie-svg{{display:block;overflow:visible}}
.kmini .on{{fill:{GROUND}}}.kmini .off{{fill:{GROUND};opacity:.2}}
.sw{{display:inline-block;width:.62em;height:.62em;margin-right:.32em;vertical-align:.02em}}
.sw.yes{{background:{S.INK["yes"]}}}.sw.partly{{background:{S.INK["partly"]}}}.sw.no{{background:{S.INK["no"]}}}.sw.unstated{{background:{GHOST};box-shadow:inset 0 0 0 2px {UNSTATED}}}
"""


def card_page(card, body, css):
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(card)} card</title>'
        f"<style>{font_faces('../fonts/')}\n{card_css()}{css}</style></head><body>{body}</body></html>\n"
    )


def home_card():
    """Only what does not change with the systems benchmarked, since link previews stay cached:
    violet, the six properties, each beside its place in the glyph; black, the site's mark and name."""
    props = "".join(
        f'<li>{key_mini(i + 1, 52)}<span class="disp">{e(p["name"])}</span></li>'
        for i, p in enumerate(S.PROPS)
    )
    css = f"""
.l{{position:absolute;left:0;top:0;width:690px;height:{CARD_H}px;background:{VIOLET};color:{GROUND};padding:50px 56px}}
.r{{position:absolute;left:690px;top:0;right:0;height:{CARD_H}px;padding:50px 52px;display:flex;flex-direction:column;justify-content:center}}
.k{{font-size:20px;font-weight:600;letter-spacing:.12em;text-transform:uppercase}}
ul{{list-style:none;margin-top:30px;display:grid;gap:14px}}
li{{display:flex;align-items:center;gap:20px}}
li .disp{{font-size:58px;line-height:1;letter-spacing:-.004em}}
.mark{{display:block;width:176px;height:176px;fill:{VIOLET}}}
.name{{font-size:104px;line-height:.86;margin-top:40px;letter-spacing:-.008em}}
.url{{font-size:19px;color:{MUTED};letter-spacing:.04em;margin-top:26px}}
"""
    body = (
        f'<div class="l"><p class="k mono">What one proof establishes</p><ul>{props}</ul></div>'
        f'<div class="r">{mark_svg(176, cls="mark")}'
        f'<p class="disp name">Inference<br>proofs</p><p class="mono url">inferenceproofs.ai</p></div>'
    )
    return card_page("home", body, css)


def system_card(sid):
    """The system page's first screen: its name on the violet band, then its pie with each property beside its slice."""
    g = glyph(sid)
    cfg = first_config(sid)
    items = "".join(
        f'<li class="p{c["n"]} {SIDE[c["n"]]}"><p class="mono pn">{e(c["name"])}</p>'
        f'<p class="disp pw"><i class="sw {STATE_CLS[c["state"]]}"></i>{e(c["word"])}</p></li>'
        for c in g["cells"]
    )
    css = f"""
.band{{position:absolute;left:0;top:0;right:0;height:206px;background:{VIOLET};color:{GROUND};padding:0 56px;overflow:hidden}}
.name{{position:absolute;left:52px;bottom:-9px;font-size:214px;line-height:.8;letter-spacing:-.012em;white-space:nowrap}}
.meta{{position:absolute;right:56px;top:40px;text-align:right;font-size:18px;line-height:1.5}}
.meta b{{display:block;font-weight:600;letter-spacing:.12em;text-transform:uppercase;font-size:17px;margin-bottom:6px}}
.rose{{position:absolute;left:56px;right:56px;top:232px;bottom:52px;display:grid;grid-template-columns:1fr 330px 1fr;
grid-template-areas:"p6 pie p1" "p5 pie p2" "p4 pie p3";column-gap:40px;align-items:center}}
.rose .pie-svg{{grid-area:pie;width:330px;height:330px;justify-self:center;align-self:center}}
ol{{display:contents;list-style:none}}
.p1{{grid-area:p1}}.p2{{grid-area:p2}}.p3{{grid-area:p3}}.p4{{grid-area:p4}}.p5{{grid-area:p5}}.p6{{grid-area:p6}}
.l{{text-align:right}}
.pn{{font-size:17px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:{VIOLET}}}
.pw{{font-size:46px;line-height:1.05;margin-top:4px;font-stretch:80%;font-weight:800}}
"""
    body = (
        f'<div class="band"><h1 class="disp name">{e(name_of(sid))}</h1>'
        f'<p class="mono meta"><b>Inference proofs</b>{e(S.MODEL_NAME[cfg["workload"]["model"]["digest"]])}<br>@{e(upstream(cfg)["commit"][:8])}</p></div>'
        f'<div class="rose">{pie_svg(g["states"], 330)}<ol>{items}</ol></div>'
    )
    return card_page(sid, body, css)


ICON = 180  # the touch icon's side, CSS px at scale 1
FAVICON = 32  # the PNG icon for clients that read no SVG icon


def icon_svg():
    """The site's icon: the hex asterisk in ground ink on the violet field."""
    parts = "".join(re.findall(r'<path d="[^"]+"/>', mark_svg(64)))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-10 -10 84 84">'
        f'<rect x="-10" y="-10" width="84" height="84" fill="{VIOLET}"/><g fill="{GROUND}">{parts}</g></svg>\n'
    )


def icon_card(size=ICON, name="icon"):
    body = f'<img src="icon.svg" width="{size}" height="{size}" alt="" style="display:block">'
    page_ = card_page(name, body, "")
    return page_.replace(
        '<html lang="en">', f'<html lang="en" data-w="{size}" data-h="{size}" data-scale="1">', 1
    ).replace(
        f"html,body{{width:{CARD_W}px;height:{CARD_H}px;",
        f"html,body{{width:{size}px;height:{size}px;",
    )


def write_cards():
    S.OG.mkdir(exist_ok=True)
    S.WRITE_TEXT(S.OG / "icon.svg", icon_svg())
    S.WRITE_TEXT(S.OG / "icon.html", icon_card())
    S.WRITE_TEXT(S.OG / "icon-32.html", icon_card(FAVICON, "icon-32"))
    S.WRITE_TEXT(S.OG / "home.html", home_card())
    for sid in S.PAGE:
        S.WRITE_TEXT(S.OG / f"{sid}.html", system_card(sid))


def write_font_faces():
    """The @font-face block in words.css, between its markers, from fonts/faces.json."""
    css = (S.HERE / "words.css").read_text()
    block = "/* fonts: written by build.py */\n" + font_faces("/fonts/") + "\n/* /fonts */"
    new = re.sub(
        r"/\* fonts: written by build.py \*/.*?/\* /fonts \*/", lambda _: block, css, flags=re.S
    )
    assert new != css or block in css, "words.css lacks the fonts markers"
    S.WRITE_TEXT(S.HERE / "words.css", new)


def write_readme():
    readme = S.HERE / "README.md"
    if not readme.exists():
        return
    table = (
        "| Word | Ink | Luminance | Contrast on the ground `"
        + GROUND
        + "` | Step from the state below |\n|---|---|---|---|---|\n"
        + "\n".join(f"| {a} | {b} | {c} | {d} | {f} |" for a, b, c, d, f in S.ladder)
        + "\n\n| Pair | Contrast |\n|---|---|\n"
        + "\n".join(f"| {n} (`{a}` on `{b}`) | {ratio(a, b):.2f}:1 |" for n, a, b in S.pairs)
    )
    txt = re.sub(
        r"<!-- ladder -->.*<!-- /ladder -->",
        "<!-- ladder -->\n" + table + "\n<!-- /ladder -->",
        readme.read_text(),
        flags=re.S,
    )
    S.WRITE_TEXT(readme, txt)
