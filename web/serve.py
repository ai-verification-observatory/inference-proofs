"""Local preview with the site's own addresses: python3 -I serve.py [port]   (default 4440)

Serves this folder as Vercel does with web/vercel.json:
- only the files its buildCommand deploys (the pages, words.css, words.js, og/*.png and *.svg,
  fonts/*.woff2); anything else, like the data or this script, answers the 404 page;
- clean addresses: /flashprove answers flashprove.html, and /flashprove.html and /flashprove/
  redirect to /flashprove; an unknown path answers 404.html with status 404;
- its redirects (/system) and the headers of every entry whose source matches, the
  Content-Security-Policy included, so the checks run the pages under the same rules.
Query strings (?v=...) are ignored, as on the site.
"""

import functools
import http.server
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
VERCEL = json.loads((HERE / "vercel.json").read_text())
REDIRECTS = {
    r["source"]: (r["destination"], 308 if r.get("permanent") else 307) for r in VERCEL["redirects"]
}
HEADERS = [(re.compile(f"^{h['source']}$"), h["headers"]) for h in VERCEL["headers"]]
DEPLOYED = re.compile(
    r"^(words\.css|words\.js|og/[^/]+\.(png|svg)|fonts/[^/]+\.woff2|[^/]+\.html)$"
)


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        path = self.path.split("?", 1)[0]
        for rx, headers in HEADERS:
            if rx.match(path):
                for h in headers:
                    self.send_header(h["key"], h["value"])
        super().end_headers()

    def redirect(self, location, status):
        self.send_response(status)
        self.send_header("Location", location)
        self.end_headers()

    def not_found(self):
        body = (HERE / "404.html").read_bytes()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_head(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path in REDIRECTS:
            self.redirect(*REDIRECTS[path])
            return None
        if path != "/" and (path.endswith("/") or path.endswith(".html")):
            clean = path.rstrip("/").removesuffix(".html").removesuffix("/index") or "/"
            self.redirect(clean, 308)
            return None
        name = "index.html" if path == "/" else path.lstrip("/")
        if not name.endswith(".html") and "/" not in name and (HERE / f"{name}.html").is_file():
            name = f"{name}.html"
        if name == "404.html" or not DEPLOYED.match(name) or not (HERE / name).is_file():
            self.not_found()
            return None
        self.path = f"/{name}"
        return super().send_head()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4440
    handler = functools.partial(Handler, directory=str(HERE))
    http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
