"""The Learn pages: the hub, one page per entry of web/learn/index.yaml and the glossary.

The words reach the renderer through the view (`S.V["learn"]`: `iproofs.site.inputs.learn` reads
web/learn/). `markdown` draws a page's text from a small, strict subset of Markdown; a construct
outside it stops the build, so a page never prints markup as text:

- `## Title` and `### Title`; paragraphs; `- ` and `1. ` lists (a line indented by two spaces
  continues its item); `|` tables with a `|---|` line under the head; fenced code;
- inline: `code`, **strong**, *emphasis*, [words](address) and [[term]] or [[term|words shown]],
  a link to the glossary entry of that name (a term the glossary lacks stops the build). An
  address is a site path ("/checks#run"), `repo:<path>` (a file of the repository at the branch
  the site is built from) or an http(s) URL;
- blocks between `:::name argument` and `:::`: `note`, `stage`, `quote`, `reading`, and the
  drawn ones, `figure`, `explore` and `measured`, whose argument names a drawing of figures.py
  and whose text is its caption.

A dash used as punctuation (U+2014, U+2013) stops the build: the site's prose uses commas,
colons or parentheses (AGENTS.md, Writing style).
"""

import html
import re

from . import state as S
from .chrome import LEARN_PAGE, footer, header, link, page
from .figures import EXPLORERS, FIGURES, MEASURED, STAGE_WORD
from .words import curly, e, quoted


class Halt(RuntimeError):
    """A page's text is outside the subset: `iproofs site build` reports it as a config error."""


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# ------------------------------------------------------------------ inline
TOKEN = re.compile(
    r"`([^`]+)`"  # 1: code
    r"|\[\[([^\]|]+)(?:\|([^\]]+))?\]\]"  # 2: a glossary term, 3: the words shown for it
    r"|\[((?:[^\[\]]|\[[^\[\]]*\])+)\]\(([^()\s]+)\)"  # 4: a link's words, 5: its address
    r"|\*\*(.+?)\*\*"  # 6: strong
    r"|\*([^*\s](?:[^*]*[^*\s])?)\*"  # 7: emphasis
)
DASH = re.compile(f"[{chr(0x2014)}{chr(0x2013)}]")  # the em dash and the en dash
STRAY = re.compile(r"[*`\\\[\]]")  # a mark the subset did not read: it would print as text


def address(url, where):
    """A link's address: a site path, a file of the repository, or an http(s) URL."""
    if url.startswith("repo:"):
        return link(url[5:])
    if url.startswith(("/", "https://", "http://", "#")) and not url.startswith(("//", "/\\")):
        return url
    raise Halt(f"{where}: the address {url!r} is neither a site path, repo:<path> nor a URL")


def inline(text, ctx):
    out, pos = [], 0

    def plain(words):
        if m := STRAY.search(words):
            raise Halt(f"{ctx['where']}: {m[0]!r} is not read as a mark here: {words.strip()!r}")
        return e(words)

    for m in TOKEN.finditer(text):
        out.append(plain(text[pos : m.start()]))
        pos = m.end()
        if m[1]:
            out.append(f"<code>{e(m[1])}</code>")
        elif m[2]:
            term = slug(m[2])
            if term not in ctx["terms"]:
                raise Halt(f"{ctx['where']}: [[{m[2]}]] is not a glossary entry")
            peek = ""
            if found := ctx.get("defs", {}).get(term):
                peek = f' data-g="{e(found[0])}" data-d="{e(found[1])}"'
            out.append(f'<a class="df" href="/{ctx["glossary"]}#{term}"{peek}>'
                       f"{inline(m[3] or m[2], ctx)}</a>")  # fmt: skip
        elif m[4]:
            out.append(f'<a href="{e(address(m[5], ctx["where"]))}">{inline(m[4], ctx)}</a>')
        elif m[6]:
            out.append(f"<strong>{inline(m[6], ctx)}</strong>")
        else:
            out.append(f"<em>{inline(m[7], ctx)}</em>")
    out.append(plain(text[pos:]))
    return "".join(out)


# ------------------------------------------------------------------ blocks
HEAD = re.compile(r"(#{2,3}) (.+)$")
ITEM = re.compile(r"(- |\d+\. )(.*)$")
RULE = re.compile(r"\|(\s*:?-+:?\s*\|)+$")


def cells(line):
    """A table row's cells; the bar inside [[term|words shown]] is not a cell's edge."""
    kept = re.sub(r"\[\[[^\]]*\]\]", lambda m: m[0].replace("|", "\0"), line.strip())
    return [c.strip().replace("\0", "|") for c in kept.strip("|").split("|")]


def table(rows, ctx):
    if len(rows) < 3 or not RULE.match(rows[1].strip()):
        raise Halt(f"{ctx['where']}: a table needs a head, a |---| line and a row")
    heads = [inline(c, ctx) for c in cells(rows[0])]
    head = "".join(f'<th scope="col">{h}</th>' for h in heads)
    # on a phone the table stacks (.mt): each cell, the row's head too, under its head's name, its
    # plain words
    lead, *names = [e(html.unescape(re.sub(r"<[^>]+>", "", h))) for h in heads]
    lead = f' data-l="{lead}"' if lead else ""
    body = ""
    for row in rows[2:]:
        first, *rest = cells(row)
        if len(rest) + 1 != len(heads):
            raise Halt(f"{ctx['where']}: a table row and its head differ in length: {row!r}")
        body += (f'<tr><th scope="row"{lead}>{inline(first, ctx)}</th>'
                 + "".join(f'<td data-l="{n}">{inline(c, ctx)}</td>'
                           for n, c in zip(names, rest, strict=True)) + "</tr>")  # fmt: skip
    return (f'<div class="tw"><table class="rt lt mt"><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></div>")  # fmt: skip


def listing(lines, ctx, cls=""):
    """A list: each item's lines joined (a continuation line is indented by two spaces)."""
    if not lines:
        raise Halt(f"{ctx['where']}: a list with no item")
    ordered = not lines[0].startswith("- ")
    items = []
    for line in lines:
        m = ITEM.match(line)
        if m and (m[1] == "- ") != ordered:
            items.append(m[2])
        elif line.startswith("  ") and items:
            items[-1] += " " + line.strip()
        else:
            raise Halt(f"{ctx['where']}: a list mixes kinds, or a line is not indented: {line!r}")
    tag = "ol" if ordered else "ul"
    lis = "".join(f"<li>{inline(i, ctx)}</li>" for i in items)
    return f'<{tag} class="{("ls " + cls).strip()}">{lis}</{tag}>'


def block(name, arg, body, ctx):
    """A `:::name argument` block; `body` is the text up to its closing `:::`."""
    where = ctx["where"]
    if name == "note":
        head = f'<p class="nh">{inline(arg, ctx)}</p>' if arg else ""
        return f'<aside class="note">{head}{markdown(body, ctx)}</aside>'
    if name == "stage":
        kind, _, title = arg.partition(" ")
        if kind not in STAGE_WORD or not title:
            raise Halt(f"{where}: a stage is `:::stage {'|'.join(STAGE_WORD)} Title`")
        hid = ctx["ids"](title)
        ctx["own"](f"h-{hid}")
        return (f'<section class="stage {kind}" id="{hid}" aria-labelledby="h-{hid}">'
                f'<p class="chip {kind}">{e(STAGE_WORD[kind])}</p>'
                f'<h3 class="sth" id="h-{hid}">{inline(title, ctx)}</h3>'
                f"{markdown(body, ctx)}</section>")  # fmt: skip
    if name == "quote":
        # a publisher's or an author's own words, with where they stand: `:::quote <address> Who`
        url, _, who = arg.partition(" ")
        if not who or not body.strip():
            raise Halt(f"{where}: a quote is `:::quote <address> <who, where>` over its words")
        paras = "".join(f"<p>{quoted(p)}</p>" for p in re.split(r"\n\s*\n", body.strip()))
        return (f'<blockquote class="said2">{paras}<cite><a href="{e(address(url, where))}">'
                f"{inline(who, ctx)}</a></cite></blockquote>")  # fmt: skip
    if name == "reading":
        return listing([ln for ln in body.split("\n") if ln.strip()], ctx, cls="reading")
    drawn = {"figure": FIGURES, "explore": EXPLORERS, "measured": MEASURED}.get(name)
    if drawn is None or arg not in drawn:
        raise Halt(f"{where}: no block `:::{name} {arg}`")
    caption = (
        f"<figcaption>{inline(' '.join(body.split()), ctx)}</figcaption>" if body.strip() else ""
    )
    cls = {"figure": "fg", "explore": "fg xp", "measured": "fg ms"}[name]
    fid = ctx["own"](f"{name[:3]}-{arg}")
    return f'<figure class="{cls}" id="{fid}">{drawn[arg]()}{caption}</figure>'


def markdown(text, ctx):
    """The blocks of one text, in order (module docstring)."""
    lines = text.split("\n")
    out, i = [], 0

    def run(test):
        """The lines from i on while `test` holds; moves i past them."""
        nonlocal i
        j = i
        while j < len(lines) and test(lines[j]):
            j += 1
        got, i = lines[i:j], j
        return got

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith(":::"):
            name, _, arg = line[3:].strip().partition(" ")
            i += 1
            body = run(lambda ln: ln.strip() != ":::")
            if i >= len(lines):
                raise Halt(f"{ctx['where']}: `:::{name}` is not closed")
            i += 1
            out.append(block(name, arg.strip(), "\n".join(body), ctx))
        elif line.startswith("```"):
            i += 1
            code = run(lambda ln: not ln.startswith("```"))
            if i >= len(lines):
                raise Halt(f"{ctx['where']}: a code fence is not closed")
            i += 1
            out.append(f'<pre class="code">{e(chr(10).join(code))}</pre>')
        elif m := HEAD.match(line):
            i += 1
            hid = ctx["ids"](m[2])
            tag, cls = ("h2", "ah") if m[1] == "##" else ("h3", "ah3")
            if tag == "h2":
                ctx.setdefault("heads", []).append((hid, plain(m[2])))
            out.append(f'<{tag} class="{cls}" id="{hid}">{inline(m[2], ctx)}</{tag}>')
        elif line.startswith("|"):
            out.append(table(run(lambda ln: ln.startswith("|")), ctx))
        elif ITEM.match(line):
            out.append(listing(run(lambda ln: bool(ITEM.match(ln)) or ln.startswith("  ")), ctx))
        else:
            para = run(lambda ln: bool(ln.strip()) and not ln.startswith((":::", "```", "#", "|"))
                       and not ITEM.match(ln))  # fmt: skip
            if not para:
                raise Halt(f"{ctx['where']}: a line the subset does not read: {line!r}")
            out.append(f"<p>{inline(' '.join(ln.strip() for ln in para), ctx)}</p>")
    return "".join(out)


def context(entry, terms, defs=None):
    """What `markdown` needs for one page: where its text is, the glossary's entries (with, in
    `defs`, each one's name and first sentence, which a link to it carries) and an id maker that
    stops the build on an id used twice (a heading, a stage, a drawing, or an id of the page's
    own frame). `markdown` adds `heads`, the page's sections, (id, words) for each `## Title`."""
    seen = set(FRAME_IDS)

    def own(hid):
        if not hid or hid in seen:
            raise Halt(f"{entry['path']}: the id {hid!r} is taken or empty: use another heading, "
                       "and name a drawing once per page")  # fmt: skip
        seen.add(hid)
        return hid

    def ids(title):
        return own(slug(re.sub(r"[`*\[\]]", "", title)))

    return {"where": entry["path"], "terms": terms, "ids": ids, "own": own,
            "glossary": glossary()["slug"], "defs": defs or {}}  # fmt: skip


# the ids every page's frame holds (chrome.py, `band`): a heading must not take one
FRAME_IDS = ("main", "live", "q", "q-list", "h-name", "gpk")
SAID = re.compile(r'^:::quote\b.*?^:::[ \t]*$|"[^"\n]*"', re.M | re.S)  # a publisher's own words
CODE = re.compile(r"^```.*?^```|`[^`\n]+`", re.M | re.S)  # code keeps its straight quotes


def text_of(entry):
    """A page's text, quotes curly, refused when its own words hold a dash used as punctuation
    (a publisher's words, between quotation marks or in a quote block, keep theirs)."""
    text = entry["text"]
    own = SAID.sub(lambda m: re.sub(r"[^\n]", " ", m[0]), text)  # the same line numbers
    if m := DASH.search(own):
        line = own.count("\n", 0, m.start()) + 1
        raise Halt(f"{entry['path']}:{line}: a dash as punctuation; use a comma, colon or brackets")
    kept = []
    held = CODE.sub(lambda m: kept.append(m[0]) or f"\0{len(kept) - 1}\0", text)
    return re.sub(r"\0(\d+)\0", lambda m: kept[int(m[1])], curly(held))


# ------------------------------------------------------------------ the pages
def tracks():
    return S.V["learn"]["tracks"]


def glossary():
    return S.V["learn"]["glossary"]


def entries():
    """Every Learn page under the hub, in reading order, then the glossary."""
    return [p for t in tracks() for p in t["pages"]] + [glossary()]


def slugs():
    """The addresses the Learn pages take (none while the tree holds no Learn words)."""
    return ["learn", *(p["slug"] for p in entries())] if S.V.get("learn") else []


def terms():
    """The glossary's entries: the id of each `### Term` of its text."""
    return {slug(m[1]) for m in re.finditer(r"^### (.+)$", glossary()["text"], re.M)}


def plain(text):
    """A text of the subset without its marks: for a line of the search index."""
    text = re.sub(
        r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]|\[([^\]]+)\]\([^)]+\)", lambda m: m[1] or m[2], text
    )
    return re.sub(r"[*`]", "", text)


def glossary_entries():
    """Each glossary term: its name, its id and the first sentence under it."""
    found = re.finditer(r"^### (.+)\n+((?:.+\n?)+)", glossary()["text"], re.M)
    return [(m[1], slug(m[1]), plain(" ".join(m[2].split())).split(". ")[0].rstrip(".") + ".")
            for m in found]  # fmt: skip


def defs():
    """Each glossary term's name and first sentence, by its id: what a link to it carries, for
    the reader who points at it or gives it focus (words.js)."""
    return {tid: (name, first) for name, tid, first in glossary_entries()}


def band(kicker, title, summary, under=""):
    """A Learn page's band: where it stands (on a track's page, the glossary at the line's right
    end), its title and summary (none when the text opens with it), then `under` (the track's
    pages, or the hub's two tracks) on the band's lower edge."""
    kick = f'<p class="kick">{kicker}</p>' if kicker else ""
    said = f'<p class="lt-s">{e(summary)}</p>' if summary else ""
    return (f'<section class="mast mast-sys lband{" lunder" if under else ""}" '
            f'aria-labelledby="h-name"><div class="mast-in">{kick}'
            f'<h1 id="h-name" class="sysname lt-h">{e(title)}</h1>{said}{under}</div></section>')  # fmt: skip


def steps(track, here):
    """The track's pages as one row of cells on the band's edge, the page in view a block of
    ground ink (it moves along the row from one page to the next); on a phone their numbers."""
    cells = "".join(
        f'<li><a class="lsc{" on" if p["slug"] == here else ""}" href="/{p["slug"]}"'
        f"{' aria-current=page' if p['slug'] == here else ''}>"
        f'<span class="lsn">{k:02d}</span><span class="lst">{e(p["title"])}</span></a></li>'
        for k, p in enumerate(track["pages"], start=1)
    )
    return f'<nav class="lsteps" aria-label="{e(track["name"])}"><ol>{cells}</ol></nav>'


def neighbours(track, k):
    """The page before this one and the page after it, each (address, label, title): before a
    track's first page the hub; after its last page the first page of the other track (or the
    glossary, with one track)."""
    pages = track["pages"]
    if k:
        before = (f"/{pages[k - 1]['slug']}", "Previous", pages[k - 1]["title"])
    else:
        before = (LEARN_PAGE, "Previous", S.V["learn"]["title"])
    if k + 1 < len(pages):
        return before, (f"/{pages[k + 1]['slug']}", "Next", pages[k + 1]["title"])
    other = [t for t in tracks() if t is not track]
    if other:
        return before, (f"/{other[0]['pages'][0]['slug']}", other[0]["name"],
                        other[0]["pages"][0]["title"])  # fmt: skip
    return before, (f"/{glossary()['slug']}", "Next", glossary()["title"])


STEP = ('<svg class="lar" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" '
        'focusable="false"><path d="M5.5 2.5 11 8l-5.5 5.5" fill="none" stroke="currentColor" '
        'stroke-width="2"/></svg>')  # fmt: skip


def strip(title, heads, place=None):
    """The page's sections as the strip that stays under the top bar (the chrome's own: words.js
    marks the section in view and slides the title in once the band is gone); on a track's page
    its place in the track at the strip's end, between the page before and the page after."""
    links = "".join(f'<a href="#{hid}">{e(words)}</a>' for hid, words in heads)
    end = ""
    if place:
        where, before, after = place
        end = (f'<p class="lpl"><a class="lpa lpb" href="{before[0]}" '
               f'aria-label="{e(before[1])}: {e(before[2])}">{STEP}</a>'
               f'<span class="lpo">{where}</span><a class="lpa" href="{after[0]}" '
               f'aria-label="{e(after[1])}: {e(after[2])}">{STEP}</a></p>')  # fmt: skip
    return (f'<div class="pnav lpn"><nav class="ps" aria-label="Sections">'
            f'<span class="ps-t" aria-hidden="true">{e(title)}</span>{links}</nav>{end}</div>')  # fmt: skip


def turn(before, after):
    """Under a page: the page before it and the page after it, the next one in cobalt."""

    def to(cls, a, label):
        return (f'<a class="tn {cls}" href="{a[0]}"><span class="tl2">{label}</span>'
                f'<span class="tt">{e(a[2])}</span></a>')  # fmt: skip

    return (f'<nav class="turn" aria-label="Previous and next page">'
            f'{to("tp", before, STEP + e(before[1]))}{to("tx", after, e(after[1]) + STEP)}</nav>')  # fmt: skip


def source_line(entry):
    """Where a page's text is kept, and where to say that it is wrong."""
    return (f'<p class="src">This page\'s text: <a href="{e(link(entry["path"]))}">{e(entry["path"])}</a>. '
            f'Wrong or unclear? <a href="{e(S.REPO_URL)}/issues/new">Tell us</a>.</p>')  # fmt: skip


def build_page(slug_):
    """One page of a track: the band (track, title, summary, the track's pages), the strip of its
    sections with its place in the track, the text, then the pages before and after."""
    found = [(t, k) for t in tracks() for k, p in enumerate(t["pages"]) if p["slug"] == slug_]
    if not found:
        raise Halt(f"no Learn page {slug_!r}")
    track, k = found[0]
    entry = track["pages"][k]
    kicker = (f'<span><a href="{LEARN_PAGE}">Learn</a> · '
              f'<a href="{LEARN_PAGE}#{e(track["id"])}">{e(track["name"])}</a></span>'
              f'<a href="/{e(glossary()["slug"])}">{e(glossary()["title"])}</a>')  # fmt: skip
    ctx = context(entry, terms(), defs())
    text = markdown(text_of(entry), ctx)
    before, after = neighbours(track, k)
    where = f"{k + 1} of {len(track['pages'])}"
    body = f"""
{header("learn", under=True)}
<main id="main" class="sys">
  {band(kicker, entry["title"], entry["summary"], steps(track, slug_))}
  {strip(entry["title"], ctx.get("heads", []), (where, before, after))}
  <div class="wrap lwrap">
    <article class="prose lpr">{text}</article>
    {turn(before, after)}{source_line(entry)}
  </div>
</main>
{footer()}"""
    return page(entry["title"], entry["summary"], body, "system learnpage", slug_, "home")


def build_glossary():
    """The glossary: its terms under their first letter (each letter a section of the strip), one
    entry per `### Term`, each an address of its own."""
    entry = glossary()
    ctx = context(entry, terms(), defs())
    intro, *found = re.split(r'(?=<h3 class="ah3")', markdown(text_of(entry), ctx))
    groups = {}
    for part in found:
        name = re.sub(r"<[^>]+>", "", re.match(r"<h3[^>]*>(.*?)</h3>", part)[1])
        groups.setdefault(name[0].upper(), []).append(f'<div class="term">{part}</div>')
    heads, sections = [], ""
    for letter, rows in groups.items():
        lid = ctx["own"](f"l-{letter.lower()}")
        ctx["own"](f"h-{lid}")
        heads.append((lid, letter))
        sections += (f'<section class="gll" id="{lid}" aria-labelledby="h-{lid}">'
                     f'<h2 class="glh" id="h-{lid}">{e(letter)}</h2>'
                     f'<div class="glt">{"".join(rows)}</div></section>')  # fmt: skip
    kicker = f'<span><a href="{LEARN_PAGE}">Learn</a> · both tracks</span>'
    body = f"""
{header("learn", under=True)}
<main id="main" class="sys">
  {band(kicker, entry["title"], "")}
  {strip(entry["title"], heads)}
  <div class="wrap lwrap">
    <article class="prose gls"><div class="gli">{intro}</div>{sections}</article>
    {source_line(entry)}
  </div>
</main>
{footer()}"""
    return page(entry["title"], entry["summary"], body, "system learnpage", entry["slug"], "home")


def build_hub():
    """The hub: the two tracks as two cells on the band's edge, each over its pages in reading
    order; then every term of the glossary."""
    lv = S.V["learn"]
    ways = "".join(
        f'<a class="lway" href="#{e(t["id"])}"><span class="lwn">{e(t["name"])}</span>'
        f'<span class="lwr">{e(t["reader"])}</span>'
        f'<span class="lwc">{len(t["pages"])} pages</span></a>'
        for t in tracks()
    )

    def track_html(t):
        rows = "".join(
            f'<li><a class="hp" href="/{p["slug"]}"><span class="hn">{k:02d}</span>'
            f'<span class="ht">{e(p["title"])}</span><span class="hs">{e(p["summary"])}</span></a></li>'
            for k, p in enumerate(t["pages"], start=1)
        )
        return (f'<section class="ltk" id="{e(t["id"])}" aria-labelledby="h-{e(t["id"])}">'
                f'<h2 class="trh" id="h-{e(t["id"])}">{e(t["name"])}</h2>'
                f'<p class="trr">{e(t["reader"])}</p><ol class="hl2">{rows}</ol></section>')  # fmt: skip

    g = glossary()
    names = "".join(f'<li><a href="/{g["slug"]}#{tid}" data-g="{e(name)}" data-d="{e(first)}">'
                    f"{e(name)}</a></li>" for name, tid, first in glossary_entries())  # fmt: skip
    both = (f'<section class="lgl" id="terms" aria-labelledby="h-terms"><h2 class="trh lgh" '
            f'id="h-terms"><a href="/{g["slug"]}">{e(g["title"])}</a></h2>'
            f'<p class="hs">{e(g["summary"])}</p><ul class="lgt">{names}</ul></section>')  # fmt: skip
    body = f"""
{header("learn")}
<main id="main">
  {band("", lv["title"], lv["lead"], f'<nav class="lways" aria-label="Tracks">{ways}</nav>')}
  <div class="wrap">
    <div class="trks">{"".join(track_html(t) for t in tracks())}</div>
    {both}
  </div>
</main>
{footer()}"""
    return page(lv["title"], lv["lead"], body, "system learnpage hub", "learn", "home")


def build_all():
    """Every Learn page by its address; none while the tree holds no Learn words."""
    if not S.V.get("learn"):
        return {}
    out = {LEARN_PAGE: build_hub(), f"/{glossary()['slug']}": build_glossary()}
    for t in tracks():
        for p in t["pages"]:
            out[f"/{p['slug']}"] = build_page(p["slug"])
    return out
