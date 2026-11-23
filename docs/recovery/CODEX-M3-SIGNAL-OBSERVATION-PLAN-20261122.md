# Signal-observation CPU breakdown

Codex owns this bounded observation: `offline_stage_timing.hpp`, the probes in
`PolyphonicPitchDetector::process_sample`, `cloud/native/CMakeLists.txt`, the
existing completion-timing runner and stage validators, their focused tests,
and worker workflow `signal-observation-stages.yml`. Claude remains an equal
active peer on distinct tracking work. This is not a new tracking policy.

## Question and fixed scope

The saved stage report from run 43776647926 puts signal observation ahead of
selection in total CPU cost. Three subsequent default-off optimizations
(exact cell sharing, packed arithmetic, narrow clearing) failed their frozen
usefulness screens. Do not repeat them. The unresolved question is which work
inside signal observation consumes that cost.

Add a default-OFF compile-only switch,
`M3_OFFLINE_SIGNAL_OBSERVATION_TIMING`, requiring `M3_OFFLINE_STAGE_TIMING`.
Sequential, non-overlapping probes split the existing signal-observation
stage into spectral trackers, group trackers, resonator cell updates, narrow
updates, and the residual `signal_observe` time. Keep all DSP expressions,
ordering, runtime flags and saved references unchanged. Production builds do
not contain these probes.

One GitHub CPU job, three fixed block-32 replays, reusing the existing runner:

| Recording | Mode | Saved callback ends |
|---|---|---|
| ordinary | current-on | 1172736 |
| ordinary | completion-midi-retention-on | 7664256, 7671744 |
| physical-long | completion-midi-retention-on | 3512640 |

Require all three complete snapshot hashes/metrics to match their pinned
uninstrumented references, timed/scored identity, zero processing allocations
and frees, complete stage totals and all four fixed callback controls. Run the
existing native tests on GitHub and the focused runner contracts. Local work
is source edits and small mock tests only. Inputs stay on the authorized
worker route. Collect the small report/log artifact once; snapshots stay remote.

## Reading rule

Report total time, calls and shares for each substage, residual work, and the
four recorded callbacks. Clock calls and changed code layout add overhead,
especially to short intervals. These measurements locate a candidate cost;
they do not prove a production speed gain, clear deadline failures, or justify
a tracking change. A follow-on optimization needs a distinct mechanism and its
own paired uninstrumented screen. No tuning, second dispatch or promotion is
part of this observation. Installed output and all prior verdicts stay fixed.

Claude's attack-zone result (a8809ac) complements the completed stable-note
timing check. Acoustic re-pluck preservation remains unmeasured; neither the
suppression percentage nor callback timing changes that conclusion. Do not
duplicate those completed analyses.

## Local preparation

All 25 focused Python runner/validator tests pass. The worker YAML parses and
all six shell blocks pass `bash -n`. One scoped source/workflow review and
`git diff --check` found no material issue. No native code or recording was
executed locally. Native execution and the output-identity checks remain for
the single GitHub job.
