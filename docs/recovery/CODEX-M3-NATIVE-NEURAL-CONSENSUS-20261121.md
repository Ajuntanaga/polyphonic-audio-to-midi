# Frozen saved-stream native/neural consensus screen

Frozen before reading candidate counts or scoring this combination, 2026-11-21.
Codex owns this bounded saved-data implementation; Claude's rolling U/D2 analysis
remains separate and is not duplicated. No audio, model, native replay or new job.

The single candidate preserves every saved CURRENT pitch span. It adds a pitch
only in the intersection of Basic Pitch arm A (measured FIFO completion clock)
and observed native selector confirmation. Exact predicate, at every serialized
native decision: `quiet == 0 && selector_pool_member == 1 && direct == 1`.
There is no pitch cutoff, energy adjustment, fit, per-label rule or sweep.

This means a directly supported pitch was offered to the native selector. It
does not require final selection and can include a DP-evicted option. It is not
called generic raw admission: grouped-unison insertion has a separate path.
Source review: selector pool diagnostics are reset each decision and populated
from actual pool entries before final DP choice. Missing candidate tuples block
confirmation. The old trace inclusion filter does not retain every pooled
candidate, so a failed recovery is not proof that a full runtime observation
would have no evidence. All available annotated rows in v5 are retained, but
that cannot be assumed for every unannotated control or the older middle trace.

Timing is conservative and fixed: trace `sample` is the zero-based sample after
processing; confirmation becomes available at
`ceil((sample + 1) / 512) * 512`. The last observed decision within each callback
wins. It remains valid for one subsequent 512-sample block only. No observation
in the next block means no continuing confirmation. A quiet or observed missing
candidate clears support. This is a chosen saved-hybrid callback projection,
not a measurement of the two detectors running together. Basic Pitch delivery
timestamps remain unchanged. Annotation, labels and rendered voices do not feed
the predicate. Labels are read only by the scorer.

Inputs are pinned in `tools/native_neural_consensus.py`:

- Bridge 44891340815 report SHA256
  `da1ba0a1e2aa0bd0df9b9db07a12344d24c683a793545e60c84d2ac4a2aec773`.
  Its collected event members carry the bridge's own hashes and horizons.
- Ordinary native trace: run44835727027, source
  `0b3fcbad7ab349c25a8ec1705f2216ce0d1271b0`, v5 raw TSV SHA256
  `b664c7ff0ce80bd4e544b647ce48688ecf181918cb7e36643370bab2eccfbd93`.
  Its local gzip SHA256 is
  `cd905b2f5c2d9e9ff0d898c87c893fe3f79ca6b388c685dd052256d421879541`.
  CURRENT raw MIDI `77e52ee4...613a` is the same run pinned by the baseline.
- Extended-middle native trace: run43736868711, source
  `fb1c4b8c0edccd460f5ba9bea1c2963997d07206`, v2 compressed SHA256
  `82781c2db888e66c2de3acda0bc904701299891f40a5d56a1bbe2ca000e0a269`.
  CURRENT raw MIDI `a52eb7d4...c601` exactly matches the baseline's explicit
  older input. This is sufficient for saved CURRENT pairing; historical Modal
  identity remains unestablished and is not claimed.

Input-pin correction before analysis: the first attempt stopped at the gzip
hash check, before reading any candidate row or scoring any combination.
The producer hashes the raw TSV before gzip (portable_unfiltered_observation.py,
lines62-65); the checkpoint's trace hash therefore names the payload. Preserve
that original pin and validate it during the one streaming parse, also recording
the compressed file hash. The stopped attempt is retained under
`build/recovery/m3-native-neural-consensus-20261121-input-pin-stop/`.
No gate, clock, input payload or selection rule changed.

A second pre-score stop found that `quiet` is `QuietDisposition` (values0..7),
not a boolean. `not_quiet` is0; the seven other dispositions remain blocked by
the frozen predicate. Validate all eight enum values and count nonzero rows as
quiet. The failed parse stopped at ordinary row62 before any combination score;
retain it under `build/recovery/m3-native-neural-consensus-20261121-quiet-schema-stop/`.
The synthetic parser test now covers all eight dispositions and rejects8.

Before scoring the candidate, reproduce CURRENT and arm A exactly using the
existing `score()` at the bridge's common support on each recording. Hash all
input members. Preserve these identities, original raw-event audits and all
per-label measurements in the report. One streaming trace pass per corpus.

Acceptance is unchanged: ordinary must gain expected-pitch samples; both
recordings must have no wrong-pitch/gap growth, no exact-set or all-expected
loss, and no per-label presence or longest-hold loss. Report occupancy segment
counts; they are not raw MIDI retriggers. A passing saved-data screen would only
justify implementation and lifecycle/corpus/runtime checks, never promotion.
A rejection stops this fixed candidate; no tuning to the observed failures.

All results are distinct-pitch sample occupancy. Same-pitch unison multiplicity,
string assignments, installed frame scores, joint CPU deadlines, physical
pluck latency and live device delivery remain separate. Installed output stays
unchanged. Full output: `build/recovery/m3-native-neural-consensus-20261121/`.
