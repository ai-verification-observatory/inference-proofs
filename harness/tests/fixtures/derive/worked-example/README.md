# Worked example (test fixture, not a result)

The hand-computed case from [RFC-0004 §Worked example](../../../../../rfcs/0004-metrics-timing-grades.md#worked-example-test-fixture-not-a-result). The inputs are invented round numbers and describe no system. `inputs.json` holds the events, release times and recorded metrics; `expected.json` holds the values computed by hand in the RFC table. Tests compare with `math.isclose(rel_tol=1e-12)` because a decimal such as 0.01 has no exact binary64 form.
