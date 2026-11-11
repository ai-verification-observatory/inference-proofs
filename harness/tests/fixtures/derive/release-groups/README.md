# Release groups (test fixture, copied from a stored run)

`releases.json` holds the fields RFC-0018 CO-1 to CO-3 read, copied unchanged from `results/v0.1/flashprove/2026-11-09-flashprove-fp-maverick-w1024-b24-prover-h200-hosted-1/run.json`: the `commit.start` and `prove.start` events (`events[].mono_ns`), each proof's `proof_id`, `request_index` and `release_mono_ns` (`proofs[]`), and the GPU count (`inputs.gpu_count.value`, 1). Nothing else of the run is copied.

The 120 proofs fall into five release groups of 24 (CO-2, group gap 1 s). The later groups' seconds per reply are 7.116, 7.136, 7.141 and 7.119 s, all within 5 % of their median, so m = (t_5 − t_1) × 1 / 96 = 7.128 GPU-seconds per reply to four significant digits (CO-3, CO-6). The run checked one reply token after a 1,024-token window at batch 24; it is a v0.1 record, not a Level 1 session.
