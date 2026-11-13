"""The drawings of a system page: bars of one row's GPU times per reply and the fidelity tracks.
Every mark is geometry from a stored value of one row or one model: no number is typed here, and
nothing is ranked across models (RFC-0018 OR-1). Each bar sits beside its labelled figure.

A bar is SVG on a viewBox VB units wide, stretched to its box (`preserveAspectRatio="none"`), so
a length is the stored value over the largest value it is drawn beside; lines keep their width
(`vector-effect`, words.css). words.css inks them.
"""

VB = 1000  # a bar's length in user units, at the largest value it is drawn beside
MIN = 4  # a part shorter than this, in user units, is also marked by a line where it ends


def svg(cls, h, body):
    return (f'<svg class="{cls}" viewBox="0 0 {VB} {h}" preserveAspectRatio="none" '
            f'aria-hidden="true" focusable="false">{body}</svg>')  # fmt: skip


def hbar(segs, top, h=12, cls="hb"):
    """One bar of consecutive parts, each (value, class), on the scale where `top` fills the box;
    a hairline track under it shows the scale's end. Class "bc" is drawn as an outline. Every
    part is drawn at its own length; one too short to see is marked by a line where it ends (a
    position on the scale, never drawn longer than its value)."""
    out = [f'<rect class="tk" y="{h / 2 - 0.5:g}" width="{VB}" height="1"/>']
    x, cuts, nibs = 0.0, [], []
    for v, c in segs:
        w = VB * v / top if top else 0
        if c == "bc":
            out.append(f'<rect class="bc" x="{x:.2f}" y=".75" width="{w:.2f}" '
                       f'height="{h - 1.5:g}"/>')  # fmt: skip
        else:
            out.append(f'<rect class="{c}" x="{x:.2f}" width="{w:.2f}" height="{h}"/>')
        x += w
        cuts.append(x)
        if w < MIN:
            nibs.append(f'<line class="nib {c}" x1="{x:.2f}" x2="{x:.2f}" y2="{h}"/>')
    out += [f'<line class="cut" x1="{c:.2f}" x2="{c:.2f}" y2="{h}"/>' for c in cuts[:-1]]
    return svg(cls, h, "".join(out + nibs))


def fid_svg(value, bar, top, kind, h=18):
    """A fidelity track from no matched token to the whole reply (`top`): the stretch up to the
    model's bar shaded, the bar a line, the replies' mean matched prefix a tick (kind: me,
    honest, damaged, bar)."""
    out = [f'<rect class="tk" y="{h / 2 - 0.5:g}" width="{VB}" height="1"/>']
    if bar is not None:
        b = VB * bar / top
        out.append(f'<rect class="fz" width="{b:.2f}" height="{h}"/>')
        out.append(f'<line class="fb" x1="{b:.2f}" x2="{b:.2f}" y2="{h}"/>')
    if value is not None:
        x = min(max(VB * value / top, 1), VB - 1)
        out.append(f'<line class="ft {kind}" x1="{x:.2f}" x2="{x:.2f}" y1="2" y2="{h - 2}"/>')
    return svg("fdt", h, "".join(out))
