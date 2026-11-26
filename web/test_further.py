"""The site of a board built by the further-reply rule (RFC-0018 CO-9, Q55) against that board:
every printed figure is a value it stores, the ladder prints each row's two multiples (or the
proving one as not measured where the board splits none) and the proving batch, the printed rates
divide to the printed total, and GPU utilisation prints under Cost only. The board is v1.0's stored
records built by the rule (`further_site`): FlashProve splits by its generation marks, SASH's v1.0
sessions hold no adapter phases, so it has no split. Run from the repository root:
uv run pytest web -q
"""

import html
import re
from typing import Any

from test_site import FIG, pages, resolve, rows

POINTER = re.compile(r"record: [^#]+#(/[^;\"]+)")


def row_html(index: str, pid: str) -> str:
    found = re.search(rf'<tr class="row" id="row-{pid}">(.*?)</tr>', index, re.S)
    assert found, pid
    return html.unescape(found[1])


def test_every_printed_figure_is_a_board_value(further_site: Any) -> None:
    """AGENTS.md rules 2 and 3 on a further-reply board: each figure names its record in the
    board and prints that stored value in its unit (the one-time work in GPU-hours, its mark in
    replies, peak memory in GB), through the renderer's own number words."""
    number = further_site.build.number
    seen = set()
    for name, text in pages(further_site.out).items():
        assert text.count('class="fig"') == len(FIG.findall(text)), name
        for title, n, said in FIG.findall(text):
            record = POINTER.search(html.unescape(title))
            assert record, (name, title)
            if not re.search(r"record: board\.json#", html.unescape(title)):
                continue  # a figure of another record (a fidelity run's)
            stored = resolve(further_site.board, record[1])
            if isinstance(stored, dict):
                want = number(stored["value"], stored["unit"])
                unit = said
                if stored["unit"] == "token/gpu_s":
                    unit = re.sub(r"^tokens/s per \S+$", want[1], said)
                assert (n, unit) == want, (name, record[1])
                seen.add(record[1].rsplit("/", 1)[-1])
    assert {"further_reply_multiple", "further_reply_proving_multiple",
            "further_reply_proving_gpu_seconds", "further_reply_generation_gpu_seconds",
            "one_time_gpu_seconds", "one_time_mark_replies", "prove_gpu_util_mean",
            "prove_gpu_memory_peak", "further_reply_tokens_per_gpu_second"} <= seen  # fmt: skip


def test_the_ladder_prints_both_multiples_and_the_batch(further_site: Any) -> None:
    """CO-9: every row prints its total multiple; a row the board splits prints its proving
    multiple, one it does not prints "not measured" and no proving figure; each row prints the
    replies one proof covers, the board's `proving_batch`. By hand on v1.0's records: FlashProve
    1,240x and 40.85x, 24 replies a proof; SASH 54,620x, no split, 1 reply a proof."""
    index = (further_site.out / "index.html").read_text()
    number = further_site.build.number
    for row in rows(further_site.board):
        text = row_html(index, row["system"])
        pointers = set(POINTER.findall(text))
        names = {p.rsplit("/", 1)[-1] for p in pointers}
        assert "further_reply_multiple" in names, row["system"]
        assert "session_multiple" not in names, row["system"]
        total = number(row["further_reply_multiple"]["value"], "ratio")[0]
        assert f'<span class="n">{total}</span>' in text, row["system"]
        proving = row["further_reply_proving_multiple"]
        assert ("further_reply_proving_multiple" in names) == (proving["value"] is not None)
        if proving["value"] is None:
            assert "not measured" in text, row["system"]
        else:
            got = number(proving["value"], "ratio")[0]
            assert f'<span class="n">{got}</span>' in text, row["system"]
        batch = row["proving_batch"]["replies"]
        assert re.search(rf">{batch:,} repl", text), row["system"]
    by = {r["system"]: r for r in rows(further_site.board)}
    assert number(by["flashprove"]["further_reply_multiple"]["value"], "ratio")[0] == "1,240"
    assert (
        number(by["flashprove"]["further_reply_proving_multiple"]["value"], "ratio")[0] == "40.85"
    )
    assert by["sash"]["further_reply_proving_multiple"]["value"] is None


def test_printed_rates_divide_to_the_printed_total(further_site: Any) -> None:
    """CO-8 as Q55 amends it: the proved rate under a row's total multiple, over a further reply,
    and its model's served rate, as printed, divide to the total printed above (2,669 / 2.153 =
    1,239.7 against 1,240x)."""
    index = (further_site.out / "index.html").read_text()
    number = further_site.build.number
    for rung in further_site.board["rungs"]:
        served = (rung["baseline"] or {}).get("reply_tokens_per_gpu_second") or {}
        for row in rung["rows"]:
            proved = row["further_reply_tokens_per_gpu_second"]
            if served.get("value") is None or proved["value"] is None:
                continue
            sv, pv, m = (float(number(v, u)[0].replace(",", "")) for v, u in (
                (served["value"], served["unit"]), (proved["value"], proved["unit"]),
                (row["further_reply_multiple"]["value"], "ratio")))  # fmt: skip
            assert abs(sv / pv - m) <= 1e-3 * m, (row["system"], sv, pv, m)
            assert "further_reply_tokens_per_gpu_second" in row_html(index, row["system"])


def test_utilisation_prints_under_cost_only(further_site: Any) -> None:
    """CO-9, point 4: GPU utilisation and peak GPU memory are diagnostics under Cost on a system
    page, never on the ladder, the Overview page or a card."""
    out = further_site.out
    for row in rows(further_site.board):
        sid = row["system"]
        for page in ("index.html", "overview.html", f"og/{sid}.html", f"{sid}.html"):
            text = html.unescape((out / page).read_text())
            for key in ("prove_gpu_util_mean", "prove_gpu_memory_peak"):
                assert (key in text) == (page == f"{sid}.html"), (page, key)
