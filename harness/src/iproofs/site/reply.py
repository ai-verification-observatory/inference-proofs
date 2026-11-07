"""A system maintainer's reply as HTML (RFC-0009 §Right of reply)."""

import html
import re

LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


def reply_html(text: str) -> str:
    """Everything escaped, then only emphasis, bullet lists and http(s) links rendered. The
    result is safe to place in a page as is: every piece of the reply was escaped here."""

    def inline(s: str) -> str:
        s = html.escape(s, quote=True)
        s = LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        return re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)

    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.splitlines()
        if lines and all(line.lstrip().startswith(("- ", "* ")) for line in lines):
            items = "".join(f"<li>{inline(line.lstrip()[2:])}</li>" for line in lines)
            out.append(f"<ul>{items}</ul>")
        elif block.strip():
            out.append(f"<p>{inline(' '.join(line.strip() for line in lines))}</p>")
    return "\n".join(out)
