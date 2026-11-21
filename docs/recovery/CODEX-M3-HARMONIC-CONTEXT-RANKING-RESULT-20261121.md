# Harmonic-context training errors: two remaining problems

The frozen screen remains rejected at the five-pitch training gate. This
saved-array diagnosis reproduces all original aggregate, per-polyphony,
per-pitch and source-use counts exactly. All 200 pass-1 source keys are
present. Eight synthetic analysis checks pass. No fitting, cutoff selection,
audio/model loading, held-out evaluation or new remote job occurred.

Run `44960075844`, source `a5f46bab45be9cf87126f21426857358c6f75b2d`,
worker `b18546e6556e84659b307f46c4b61037c5bc7d98` remains final. Evidence
artifact `14729601382` was collected once; its 4,582,838-byte archive matches
server SHA-256 `bf18a1b950d5146b489d07a7b060d5fd34b70b132636fc1a4786918d06377359`.
Only the report-pinned training predictions and mixture plan were extracted.
The model is unextracted inside the archive, never loaded. Archive plus
extracted members use 9,097,452 bytes.

## Frozen results and diagnosis

CURRENT five-pitch complete sets remain **1,547/2,529 (61.17%)**. TARGET is
1,771 sets (the integer minimum for 70%), leaving 224 sets / 8.86 percentage
points. PROGRESS is 1,547/1,771 = 87.35% of this training gate, not project
completion. Global training precision remains 43,101/(43,101+433) = 99.0054%.
The cutoff remains `0.7022203803062439`; installed scores are unchanged.

| Five-pitch outcome | Mixtures |
|---|---:|
| Complete set | 1,547 |
| Missing expected pitches only | 863 |
| Extra pitches only | 48 |
| Both missing and extra | 71 |

Of the 982 incomplete sets, 863 (87.88%) contain only missing pitches.
However, the ordering diagnosis divides those 982 failures almost evenly:

- 482 rank **every true pitch above every false pitch**, but the frozen
  cutoff does not recover the full set.
- 500 rank a false pitch above the weakest true pitch; none is tied.

An oracle that knew each mixture's targets could choose a separate threshold
for 2,029/2,529 sets (80.23%). This is an ordering bound, not an implementable
decision rule or measured improvement. Of the 1,164 missed five-pitch targets,
577 beat every false pitch and 587 do not. A global threshold reduction does
not solve this ordering problem, and the frozen cutoff was already chosen
for maximum training true positives at at least 99% precision.

## Where the missing pitches concentrate

Scheduled gain is relative to the strongest scheduled component in the same
mixture; it is not measured mixture power. Five-pitch results alone:

| Relative gain | Missing / expected pitches | Miss rate |
|---|---:|---:|
| -24 dB | 471/1,492 | 31.57% |
| -18 dB | 348/2,210 | 15.75% |
| -12 dB | 195/2,501 | 7.80% |
| -6 dB | 94/2,467 | 3.81% |
| 0 dB | 56/3,975 | 1.41% |

The -24/-18 dB groups contribute 819/1,164 misses (70.36%) while accounting
for 3,702/12,645 targets (29.28%). Five-pitch miss rates for pitches unrelated
to another target by the frozen harmonic intervals are 536/7,554 (7.10%);
above-only 272/2,468 (11.02%), below-only 324/2,477 (13.08%), and both
32/146 (21.92%). The full report also retains false-output opportunity
denominators. These are associations, not proof of harmonic masking; gain,
pitch and source content can still differ within each group.

## Next design and limits

The current trainer uses mean binary cross-entropy across pitches. The next
distinct design to specify is a complete-set training objective that also
penalizes the weakest true / strongest false ordering, while retaining the
absolute pitch loss and silence constraint. This is a hypothesis, not a
demonstrated fix. Keep architecture, source roles and mixture schedule fixed
to make the objective change interpretable; do not retune this completed
screen's cutoff or use the oracle labels at inference.

Acceptance remains at least 99% training precision, at least 80% recall,
zero silence extras, and at least 70% complete sets overall and separately
for three, four and five pitches, followed by both untouched source roles
and continuous benefit/non-regression gates. No next job is queued.

All 555 original source labels remain intact, including unresolved source
content uncertainty. Training scores do not establish transfer, note attacks,
holds, string assignment, unisons, MIDI delivery, native timing or live
readiness. Claude is paused; no fresh Claude review is claimed. The broader
live-readiness goal remains active.

Evidence: `build/recovery/m3-harmonic-context-ranking-20261121/report.json`
and `details.json.gz`; collection receipt under
`build/github-results/harmonic-context-learning-44960075844/`.
The predeclared plan is `CODEX-M3-HARMONIC-CONTEXT-RANKING-PLAN-20261121.md`.
