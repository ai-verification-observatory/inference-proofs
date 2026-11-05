// The release loader against the golden index (harness/tests/golden/index/v0.1.json), placed in a
// temporary checkout whose systems/, workloads/ and reference/ link to this repository.
import { test } from "node:test";
import assert from "node:assert/strict";
import { cpSync, mkdirSync, mkdtempSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { load, newestRelease, releaseStatus, served, tally } from "./release.ts";
import { notReached, ROOT } from "./repo.ts";

const GOLDEN = path.join(ROOT, "harness/tests/golden/index/v0.1.json");

function checkout(releases: Record<string, string | null> = { "v0.1": null }) {
  const root = mkdtempSync(path.join(tmpdir(), "iproofs-web-"));
  for (const d of ["systems", "workloads", "reference"]) symlinkSync(path.join(ROOT, d), path.join(root, d));
  for (const [id, record] of Object.entries(releases)) {
    mkdirSync(path.join(root, "releases", id), { recursive: true });
    cpSync(GOLDEN, path.join(root, "releases", id, "index.json"));
    if (record) writeFileSync(path.join(root, "releases", id, "release.yaml"), record);
  }
  return root;
}

const RECORD = 'review_window: {opens: "2026-11-01", closes: "2026-11-15"}\nfreeze_date: "2026-11-16"\nsponsors: []\n';

test("no releases directory: the mock path, labelled mock", () => {
  const root = mkdtempSync(path.join(tmpdir(), "iproofs-web-"));
  assert.equal(newestRelease(root), null);
  const d = load(root, "2026-11-05");
  assert.equal(d.release.status, "mock");
  assert.ok(d.configurations.every((c) => Object.values(c.statistics).every((q) => q.mock)));
});

test("the newest release is picked by version number", () => {
  assert.equal(newestRelease(checkout({ "v0.9": null, "v0.10": null, "v0.2": null })), "v0.10");
});

test("golden index: configuration, runs and statistics copied with their labels", () => {
  const d = load(checkout(), "2026-11-05");
  assert.equal(d.release.id, "v0.1");
  assert.equal(d.configurations.length, 1);
  const c = d.configurations[0];
  assert.deepEqual([c.system, c.configuration, c.workload, c.profile, c.effective_tier], ["fake", "default", "fake-tiny-ci", "ci-cpu", "reported"]);
  assert.equal(c.insufficient_repetitions, false);
  assert.deepEqual(
    c.runs.map((r) => [r.run_id.slice(-1), r.status]),
    [["1", "included"], ["2", "included"], ["3", "included"], ["4", "ineligible"], ["5", "superseded"]],
  );
  const rate = c.statistics["rate_prove.steady"];
  assert.equal(rate.value, 36.0); // copied from the index, not recomputed
  assert.deepEqual([rate.unit, rate.scope, rate.grade, rate.tier, rate.source.ref], ["token/s", "prove.steady", "derived", "reported", "derive:D-STAT@0.1.0.dev0"]);
  assert.deepEqual(rate.stats, { max: 36, mean: 36, min: 36, n: 3, n_failed: 0, stdev: 0 });
  assert.equal(rate.pointer, "releases/v0.1/index.json#/configurations/0/statistics/rate_prove.steady");
  assert.equal(rate.mock, undefined);
  const gpu = c.statistics.prove_gpu_memory_peak;
  assert.deepEqual([gpu.value, gpu.null_reason], [null, "not_applicable"]);
});

test("golden index: systems, workloads, cards, controls and targets", () => {
  const d = load(checkout(), "2026-11-05");
  assert.deepEqual(d.systems.map((s) => [s.name, s.kind]), [["fake", "test"]]);
  const card = d.systems[0].cards[0];
  // systems/fake/claims/default.yaml is not in the repository: shown as missing, never as "not stated" or unreviewed
  assert.equal(card.reviewed_by, null);
  assert.equal(card.relation, "not in this checkout");
  assert.deepEqual([d.workloads[0].id, d.workloads[0].division, d.workloads[0].system, d.workloads[0].prompt_tokens], ["fake-tiny-ci", "open", "fake", 8]);
  // hand count: 5 rejected + 2 invalid_call in the expected set, 1 not_applicable not counted
  assert.deepEqual(tally(d.controls), { passed: 7, failed: 0, other: 1 });
  assert.equal(d.controls[0].items, null);
  assert.deepEqual([d.targets, d.evaluations, d.reproductions], [[], [], []]);
  assert.equal(d.release.reference_file, "reference/v0.1.yaml");
});

test("draft index: a release candidate until the review window closes and the freeze date comes", () => {
  assert.equal(load(checkout(), "2026-11-05").release.status, "candidate"); // no release.yaml
  assert.equal(load(checkout(), "2026-11-05").release.sponsors, null);
  assert.equal(load(checkout({ "v0.1": RECORD }), "2026-11-10").release.status, "candidate");
  assert.equal(load(checkout({ "v0.1": RECORD }), "2026-11-15").release.status, "candidate");
  const after = load(checkout({ "v0.1": RECORD }), "2026-11-16").release;
  assert.deepEqual([after.status, after.freeze_date, after.review_window?.closes], ["published", "2026-11-16", "2026-11-15"]);
  assert.equal(releaseStatus({ freeze_date: "2026-11-16" }, "2027-01-01"), "candidate"); // no window recorded
});

test("reference rows sit next to the rows they serve, in S5 order otherwise (mock data)", () => {
  const d = load(mkdtempSync(path.join(tmpdir(), "iproofs-web-")));
  const keys = served(d.configurations, d).map((c) => `${c.system} ${c.workload}`);
  assert.deepEqual(keys, [
    "flashprove fp-maverick-w1024-b1",
    "flashprove fp-maverick-w1024-b24",
    "ref-serve fp-maverick-w1024-b24",
    "sash sash-l31-8b-c1024",
    "sash sash-l31-8b-c4096",
    "ref-recompute sash-l31-8b-c4096",
    "ref-serve sash-l31-8b-c4096",
  ]);
});

test("maintainers: [] reads as not reached; reference and test systems have no such field", () => {
  assert.equal(notReached("sash"), true);
  assert.equal(notReached("flashprove"), true);
  assert.equal(notReached("ref-serve"), false);
  assert.equal(notReached("fake"), false);
});
