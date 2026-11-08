"""A stand-in for `llama-server` in the CPU tests: the same command line, `/health` and
`/completion` over HTTP on the loopback address, with synthetic outputs. Nothing here is a
capture of the real server; its replay tests come from the first GPU run (README §Capture).

FAKE_MODE selects a failure: `die` (exits 3 while loading), `crash` (aborts with exit code 134
on the first completion request, after a synthetic allocation error line, as a server that runs
out of GPU memory mid-request does), `bos` (evaluates one more prompt token than sent),
`http500` (every completion fails) or `ok`.
"""

import argparse
import json
import os
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

EXPECTED = {"temperature": 0.0, "n_probs": 0, "repeat_penalty": 1.0, "presence_penalty": 0.0,
            "frequency_penalty": 0.0, "cache_prompt": False, "return_tokens": True,
            "stream": False}  # fmt: skip


class Handler(BaseHTTPRequestHandler):
    mode: ClassVar[str] = "ok"
    barrier: ClassVar[threading.Barrier]
    health_calls: ClassVar[int] = 0

    def log_message(self, format: str, *args: object) -> None:
        print("http:", format % args, flush=True)

    def reply(self, status: int, doc: object) -> None:
        data = json.dumps(doc).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        Handler.health_calls += 1
        if Handler.health_calls <= 2:  # loading, as the real server answers while it loads
            self.reply(503, {"error": {"code": 503, "message": "Loading model"}})
        else:
            self.reply(200, {"status": "ok"})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.mode == "crash":
            print("CUDA error: out of memory (synthetic)", flush=True)
            os._exit(134)
        wrong = {k: body.get(k) for k, v in EXPECTED.items() if body.get(k) != v}
        try:  # every request of a batch must be in flight at once, one per slot
            slot = self.barrier.wait()
        except threading.BrokenBarrierError:
            self.reply(500, {"error": {"message": "requests of a batch arrived one by one"}})
            return
        if wrong or self.mode == "http500":
            self.reply(500, {"error": {"message": f"unexpected fields {wrong}"}})
            return
        prompt, n = body["prompt"], body["n_predict"]
        tokens = [sum(prompt) % 7] * n
        self.reply(200, {"index": 0, "content": "", "tokens": tokens, "id_slot": slot,
                         "stop": True, "tokens_predicted": n, "truncated": True,
                         "tokens_evaluated": len(prompt) + (self.mode == "bos"),
                         "stop_type": "limit", "tokens_cached": len(prompt) + n})  # fmt: skip


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("-m", required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("-np", type=int, required=True)
    args, _ = p.parse_known_args()
    print("fake llama-server", sys.argv[1:], flush=True)
    leaked = sorted(k for k in os.environ if k.startswith("LLAMA_ARG_"))
    if leaked or "CUDA_CACHE_PATH" not in os.environ:
        print(f"environment: LLAMA_ARG_* {leaked}, CUDA_CACHE_PATH unset", flush=True)
        return 4
    Handler.mode = os.environ.get("FAKE_MODE", "ok")
    if Handler.mode == "die":
        print("ggml_backend_cuda_buffer_type_alloc_buffer: out of memory (synthetic)", flush=True)
        return 3
    Handler.barrier = threading.Barrier(args.np, timeout=10)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    server.serve_forever()
    print("fake llama-server stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
