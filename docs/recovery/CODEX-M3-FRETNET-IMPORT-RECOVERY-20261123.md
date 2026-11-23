# FretNet import recovery — 2026-11-23

Run 45206977346 failed before either protected recording was processed.
This is a harness failure, not a measured FretNet rejection. The pinned model
and four reference assets downloaded with matching hashes; the runner reached
the reference stage, then raised `AttributeError: No librosa.core attribute
constantq`. Its partial reference calculations were not saved as completed
checks. No reference pass or corpus score is claimed.

The cause is access through librosa's lazy public namespace. The recovery
imports the exact `librosa.core.constantq` module explicitly and calls the same
private frame-count helper with the same arguments. The synthetic regression
test now supplies a public namespace without that attribute. All 66 adapter,
runner, scoring and lifecycle tests pass; no local audio or model execution.
Source verification run 45206913716 also passed for the original attempt.

The 8,701-byte report archive was collected once; server SHA-256
`534a15808690bba41eea3ca82afd98b2aa655763e54d12d743254fbab35bc4e2`
matches. Receipt: `build/github-results/fretnet-comparison-45206977346/collection.json`.
Report SHA-256: `eac207a1562d07ac1c7996cb0d41f04c96dfa67bf1ce8f1c8b28500d3d2c80b6`.
No bulk evidence artifact was produced. The failed attempt is final and is not
to be polled, redownloaded or rerun.

One new harness-only recovery dispatch is prepared under the existing CPU-job
authorization, using the unchanged `fretnet-comparison.yml` worker. This is the
same frozen scientific comparison, which has not executed on either corpus.
Specification SHA-256 remains
`4e092ed584e31ba6acd69d9c89409afd8e479c8efda262c2f5aa21257e2b5826`.
Model, inputs, decoding, timing convention and every acceptance threshold are
unchanged. A numerical reference mismatch still stops before corpus inference;
it is not permission to relax a tolerance or tune the detector.

Codex carries this runner recovery. Claude's ordinary 58-event acoustic lane
remains separate and may proceed independently. Installed output, defaults and
scoreboard remain unchanged. The seven-event acoustic result still does not
establish general re-pluck preservation.
