"""ref-fidelity on CPU: one `reference` call against fake llama.cpp tools (converter, quantizer,
server, perplexity), so the call's outcomes, files and records are checked without a GPU."""

import importlib.machinery
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from iproofs.provenance import dockerfile_problems
from iproofs.schema import SchemaRegistry

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parent
ROOT = SYSTEM.parents[1]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
N_OUT = 512


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    for name, sub in (("IPROOFS_IO", "io"), ("IPROOFS_MODELS", "models")):
        (tmp_path / sub).mkdir()
        monkeypatch.setenv(name, str(tmp_path / sub))
    monkeypatch.setenv("IPROOFS_SYSTEM_YAML", str(SYSTEM / "system.yaml"))
    loader = importlib.machinery.SourceFileLoader("ref_fidelity", str(SYSTEM / "entrypoint"))
    spec = importlib.util.spec_from_loader("ref_fidelity", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


PROMPT_LEN = 512


class Scripted:
    """A llama-server `/completion` that follows a fixed full reply per prompt and stops after
    an end-of-generation token at the given reply positions (stop_type "eos"), else at the
    requested count ("limit"), as the server does at the pin."""

    def __init__(self, full: "Callable[[list[int]], list[int]]", eos: "tuple[int, ...]") -> None:
        self.full, self.eos = full, eos
        self.prompts: list[list[int]] = []

    def complete(self, prompt: list[int], n: int) -> tuple[list[int], str]:
        self.prompts.append(prompt)
        start = len(prompt) - PROMPT_LEN
        reply = self.full(prompt[:PROMPT_LEN])
        for i in range(start, start + n):
            if i in self.eos:
                return reply[start : i + 1], "eos"
        return reply[start : start + n], "limit"


def fake_tools(module: ModuleType, fail: set[str]) -> list[list[str]]:
    """The llama.cpp programs, replaced: each writes what the real one would, from its argv."""
    calls: list[list[str]] = []

    def run_tool(argv: list[str], log: Path, env: dict[str, str] | None = None) -> str:
        calls.append(argv)
        name = Path(argv[1] if argv[0] == "python3" else argv[0]).name
        if name in fail:
            raise module.ToolFailed(f"{name} exited 1: out of memory")
        text = "ok\n"
        if name == "convert_hf_to_gguf.py":
            Path(argv[argv.index("--outfile") + 1]).write_text("model reference")
        elif name == "llama-quantize":
            Path(argv[2]).write_text(f"model {argv[3]}")
        elif name == "llama-perplexity":
            base = Path(argv[argv.index("--kl-divergence-base") + 1])
            if "--kl-divergence" in argv:
                text = "Mean    KLD:   0.012300 ±   0.000100\n"
            else:
                base.write_text("logits")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(text)
        return text

    class Server(Scripted):
        def __init__(self, model: Path, slots: int, ctx: int, log: Path) -> None:
            kind = model.read_text().split()[-1]
            # the reference and Q8_0 agree and end a sequence at token 49; Q4_K_M diverges
            # after 100 tokens and never ends one
            eos = () if kind == "Q4_K_M" else (49,)
            super().__init__(lambda p: [p[0]] * 100 + [p[0] if kind != "Q4_K_M" else 7] * 412,
                             eos)  # fmt: skip

        def detokenize(self, tokens: list[int]) -> str:
            return f"text {len(tokens)}"

        def stop(self) -> None:
            pass

    setattr(module, "run_tool", run_tool)  # noqa: B010 (a module loaded from a file)
    setattr(module, "make_server", Server)  # noqa: B010
    return calls


def job(io: Path) -> dict[str, object]:
    prompts = [[i] * 512 for i in range(1, 4)]
    (io / "prompts.jsonl").write_text("".join(json.dumps(p) + "\n" for p in prompts))
    (io / "kl-texts.jsonl").write_text(json.dumps([5] * 512) + "\n")
    return {"subcommand": "prove", "call": "reference", "rung": "llama-3.1-8b",
            "model_dir": "/models", "dtype": "bf16", "prompts_file": "/io/prompts.jsonl",
            "kl_texts_file": "/io/kl-texts.jsonl", "output_tokens": N_OUT,
            "kl": {"tokens": 512, "texts": 1}, "slots": 2, "replies": True,
            "controls": [{"id": "reference-2", "kind": "honest", "recipe": "rerun"},
                         {"id": "q8_0", "kind": "honest", "recipe": "quantize", "type": "Q8_0"},
                         {"id": "q4_k_m", "kind": "honest", "recipe": "quantize",
                          "type": "Q4_K_M"},
                         {"id": "drop-every-4th-block", "kind": "damaged",
                          "recipe": "drop_blocks", "every": 4}]}  # fmt: skip


def test_reference_call_records_each_control(adapter: ModuleType, tmp_path: Path) -> None:
    io = tmp_path / "io"
    fake_tools(adapter, fail={"drop_blocks.py"})
    out = adapter.prove(job(io))
    assert REGISTRY.errors("adapter-out/1", out) == []
    status = json.loads((io / "fidelity/status.json").read_text())
    assert status["reference"]["status"] == "ok"
    assert status["kl_base"]["status"] == "ok"
    controls = status["controls"]
    states = {k: v["status"] for k, v in controls.items()}
    assert states == {"reference-2": "ok", "q8_0": "ok", "q4_k_m": "ok",
                      "drop-every-4th-block": "failed"}  # fmt: skip
    assert "exited 1" in controls["drop-every-4th-block"]["cause"]
    reference = [json.loads(x) for x in (io / "fidelity/replies/reference.jsonl").read_text()
                 .splitlines()]  # fmt: skip
    q4 = [json.loads(x) for x in (io / "fidelity/replies/q4_k_m.jsonl").read_text().splitlines()]
    assert [len(r) for r in reference] == [N_OUT] * 3
    assert (reference[1][:2], q4[1][99:101]) == ([2, 2], [2, 7])
    assert controls["q8_0"]["kl_log"] == "fidelity/kl/q8_0.log"
    assert status["reference"]["continuations"] == [1, 1, 1]
    assert (controls["q8_0"]["continuations"], controls["q4_k_m"]["continuations"]) == (
        [1, 1, 1], [0, 0, 0])  # fmt: skip
    # every file the call built is gone; the KL base stays for later calls
    assert sorted(p.name for p in (io / "work").glob("*.gguf")) == []
    assert (io / "work/kl-base.kld").is_file()
    assert (io / "work/kl.txt").read_text() == "text 512"


def test_reference_conversion_failure_ends_the_call(adapter: ModuleType, tmp_path: Path) -> None:
    fake_tools(adapter, fail={"convert_hf_to_gguf.py"})
    with pytest.raises(SystemExit, match=r"convert_hf_to_gguf\.py exited 1"):
        adapter.prove(job(tmp_path / "io"))
    status = json.loads((tmp_path / "io/fidelity/status.json").read_text())
    assert status["reference"]["status"] == "failed"


def test_requests_are_greedy_and_keep_end_tokens(adapter: ModuleType) -> None:
    body = adapter.completion_body([1, 2, 3], N_OUT)
    assert (body["n_predict"], body["ignore_eos"], body["temperature"], body["samplers"],
            body["cache_prompt"], body["return_tokens"]) == (
        N_OUT, False, 0.0, ["temperature"], False, True)  # fmt: skip


def test_end_token_stays_in_the_reply_and_generation_continues(adapter: ModuleType) -> None:
    """End tokens at reply positions 0, 10 and 511: two continuations (the last one ends the
    reply), each sending prompt + reply so far, end tokens included."""
    prompt = list(range(1000, 1000 + PROMPT_LEN))
    full = list(range(N_OUT))
    server = Scripted(lambda p: full, (0, 10, 511))
    reply, continuations = adapter.greedy_reply(server, prompt, N_OUT)
    assert (reply, continuations) == (full, 2)
    assert [len(p) - PROMPT_LEN for p in server.prompts] == [0, 1, 11]
    assert server.prompts[2] == prompt + full[:11]
    stopped = Scripted(lambda p: full[:20], ())  # stops short with no end token
    with pytest.raises(adapter.ToolFailed, match="stopped"):
        adapter.greedy_reply(stopped, prompt, N_OUT)


def test_dockerfile_rules() -> None:
    lock = (SYSTEM / "inputs.lock").read_text()
    assert dockerfile_problems((SYSTEM / "Dockerfile").read_text(), lock) == []
