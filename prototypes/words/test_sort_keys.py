"""Sort keys of the home figures against hand-computed cases from _data/site.json.

Run: python3 -m pytest test_sort_keys.py   (or: python3 test_sort_keys.py)
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build

ROWS = {r['system']: r for r in build.H5['rows'] if r['kind'] == 'prover'}
K = {sid: build.row_keys(r) for sid, r in ROWS.items()}


def close(a, b):
    return abs(a - b) <= 1e-9 * max(1.0, abs(b))


def test_proof_size_in_bytes():
    # printed "18.78 MB" and "19.83 GB": 18.78 x 10^6 B and 19.83 x 10^9 B, so MB sorts before GB
    assert close(K['flashprove']['published']['proof_size'], 18_780_000)
    assert abs(K['sash']['published']['proof_size'] - 19.83e9) <= 0.005e9
    assert K['flashprove']['published']['proof_size'] < K['sash']['published']['proof_size']
    # run here (MOCK): "18.78 MB" against "19.80 GB"
    assert K['flashprove']['run']['proof_size'] < K['sash']['run']['proof_size']
    assert close(K['sash']['run']['proof_size'], 19_800_000_000)


def test_check_time_in_seconds():
    # published 16.84 s against 119.1 s; run here (MOCK) 3.120 s against 121.3 s
    assert close(K['flashprove']['published']['check_time'], 16.84)
    assert abs(K['sash']['published']['check_time'] - 119.1) <= 0.05
    assert close(K['flashprove']['run']['check_time'], 3.12)
    assert abs(K['sash']['run']['check_time'] - 121.3) <= 0.05


def test_covers_in_positions():
    assert K['flashprove']['published']['covers'] == 1024
    assert K['sash']['published']['covers'] == 4608
    # positions one proof covers, by the workload records: 1,024 prompt; 4,096 prompt and 512 output
    w = build.site['workloads']
    assert K['flashprove']['run']['covers'] == w['fp-maverick-w1024-b24']['one_proof_covers']['tokens_counted']
    assert K['sash']['run']['covers'] == w['sash-l31-8b-c4096']['one_proof_covers']['tokens_counted'] == 4096 + 512


def test_overhead_ratio_and_missing():
    assert close(K['flashprove']['published']['overhead'], 71.4)
    assert K['sash']['published']['overhead'] is None  # "Not published"
    assert K['flashprove']['run']['overhead'] is None  # "No value"
    assert round(K['sash']['run']['overhead']) == 1583


def test_units_normalise():
    assert build.UNIT['GB'] / build.UNIT['MB'] == 1000
    assert build.UNIT['min'] == 60 * build.UNIT['s']
    n, half = build.shown_number('19.83 GB')
    assert close(n, 19.83e9)
    assert close(half, 0.005e9)
    n, half = build.shown_number('1,583×')
    assert n == 1583
    assert half == 0.5
    assert build.shown_number('Not published') is None


def test_orders_agree_with_the_data():
    # the data's own sorted orders (overview.sort_pages), prover rows only, give the same order
    ids = {r['id']: sid for sid, r in ROWS.items()}
    for sp in build.OV['sort_pages']:
        col = next((c for c, w in build.SORT_WORDS.items() if w == sp['key']), None)
        if col is None:
            continue
        want = [ids[i] for i in sp['order'] if i in ids]
        have = [k for k in K if K[k][sp['view']][col] is not None]
        have.sort(key=lambda s: K[s][sp['view']][col], reverse=sp['dir'] == 'desc')
        have += sorted(k for k in K if K[k][sp['view']][col] is None)
        assert have == want, (sp['view'], col, sp['dir'], have, want)


def test_sort_options_words():
    opts = dict(build.sort_options())
    assert opts['system-asc'] == 'System, A to Z'
    assert opts['proof_size-asc'] == 'Proof size, small to large'
    assert opts['check_time-desc'] == 'Check time, long to short'
    assert len(opts) == 10


def test_home_figures_show_spread():
    # every figure whose data holds a SPREAD line shows its sample size and range on the home row,
    # also when the cell stores no other label lines (SASH run here: n_failed = 1)
    seen = 0
    for r in ROWS.values():
        for col in build.COLS:
            for view in ('published', 'run'):
                x = r['cells'][col][view]
                sp = build.card_line(x, 'SPREAD')
                if not sp or not x.get('value'):
                    continue
                lines = build.fallback_lines(x)
                n, rng = sp['v'].split(' · ')[:2]
                assert lines[:2] == [n, rng], (r['id'], col, view, lines)
                seen += 1
    assert seen == 4


if __name__ == '__main__':
    for name, f in list(globals().items()):
        if name.startswith('test_'):
            f()
            print('ok', name)
