import { test } from "node:test";
import assert from "node:assert/strict";
import { sig4, stats } from "./format.ts";
import { configurations } from "./mock.ts";

test("sig4 keeps 4 significant digits", () => {
  assert.equal(sig4(3683.298), "3,683");
  assert.equal(sig4(1.25105), "1.251");
  assert.equal(sig4(111.23), "111.2");
  assert.equal(sig4(0.0042916), "0.004292");
  assert.equal(sig4(19_800_000_000), "1.980e10");
  assert.equal(sig4(0), "0");
  assert.equal(sig4(null), "null"); // all repetitions failed: no mean, min or max
  assert.equal(sig4(1), "1");
  assert.equal(sig4(4608), "4,608");
  assert.equal(sig4(122_880), "122,900");
});

test("stats against a hand-computed case", () => {
  // 2, 4, 6: mean 4, sample variance (4 + 0 + 4) / 2 = 4, sd 2
  assert.deepEqual(stats([2, 4, 6], 1), { n: 3, n_failed: 1, mean: 4, stdev: 2, min: 2, max: 6 });
  assert.equal(stats([5]).stdev, 0);
  assert.throws(() => stats([]));
});

test("D-RATE-S on the RFC-0004 hand-computed case: 5,000 tokens / 125 s = 40 token/s", async () => {
  const { rate } = await import("./mock.ts");
  assert.equal(rate(5000, 125), 40);
});

test("mock rows are ordered alphabetically, never by a metric (RFC-0009 S5)", () => {
  const keys = configurations.map((c) => `${c.system}\u0000${c.workload}\u0000${c.profile}`);
  assert.deepEqual(keys, [...keys].sort());
});

test("every mock statistic carries unit, grade, tier and a source", () => {
  for (const c of configurations)
    for (const [id, q] of Object.entries(c.statistics)) {
      assert.ok(q.unit && q.grade && q.tier && q.source.ref, `${c.system} ${id}`);
      assert.ok(q.value !== null || q.null_reason, `${c.system} ${id} null without reason`);
    }
});
