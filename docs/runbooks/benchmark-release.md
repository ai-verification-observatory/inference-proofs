# Benchmark release

Checklist for a benchmark release (`v<release>`), from [docs/spec/09-release-and-versioning.md §Release checklists](../spec/09-release-and-versioning.md#release-checklists). Each step names the RFC section that defines it. Do every step in order; a step that fails stops the release.

1. The RFC commit is named in `release.yaml` ([RFC-0009 §Release record](../../rfcs/0009-results-and-publication.md#release-record)).
2. The reference file is merged with the price, its date and pinned driver, CUDA and runtime versions ([RFC-0006 §Reference file](../../rfcs/0006-reference-hardware-and-cost.md#reference-file), [RFC-0006 §Cost basis](../../rfcs/0006-reference-hardware-and-cost.md#cost-basis)).
3. All runs are merged. Every run is eligible, or listed as ineligible with its reason ([RFC-0014 §Eligibility](../../rfcs/0014-provenance-and-integrity.md#eligibility)).
4. The release lists the claim cards by digest ([RFC-0002 §Claim class](../../rfcs/0002-claim-card.md#claim-class), [RFC-0009 §Release record](../../rfcs/0009-results-and-publication.md#release-record)).
5. The report is drafted from [reports/TEMPLATE.md](../../reports/TEMPLATE.md) ([RFC-0009 §Reports](../../rfcs/0009-results-and-publication.md#reports)).
6. `iproofs release freeze` is run, `index.json` is merged, and the tag `v<release>` is placed on that commit ([RFC-0009 §Freeze algorithm](../../rfcs/0009-results-and-publication.md#freeze-algorithm)).
7. `iproofs site build` writes `web/` from the frozen release, and the site is published from the tagged commit ([RFC-0009 §Site](../../rfcs/0009-results-and-publication.md#site)).
