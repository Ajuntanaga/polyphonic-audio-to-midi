# Native joint rapid-release reset: frozen screen

Codex owns the detector/replay integration, its tests, one remote wrapper and
`joint-rapid-reset.yml` for this screen. Claude continues independent saved-result
analysis with equal authority. No acknowledgement is required. This follows the
rejected saved-span latch; that result is not being rerun or reclassified.

## Mechanism and clock

The offline-only flag is `--diagnostic-joint-rapid-release SUPPORT.tsv`.
At the existing `QuietDisposition::rapid_mute_ratio` decision, an active
candidate is released only when model support has been primed by its first
global NoteOn and the candidate's rendered MIDI pitch is absent from that
support. A supported pitch vetoes the release. On successful native NoteOff,
clear the existing CandidateState just as the normal release path does.
On a refused NoteOff retain state and do not attempt a second release in the
same decision. The ordinary selection, evidence, attack and lane rules govern
any subsequent activation. No explicit reopening, new energy threshold,
duration cutoff, label exception or model inference is added.

Support consists of the pinned cropped-adapted ONNX events from run45034216124
on their measured `emitted_ns` clock. Convert time to the first sample at or
after delivery. Consume events before that sample, in original order for ties;
never consult later events. This clock is independent of host block size.
An earlier drafting idea of callback-boundary delivery was dropped before
implementation because it would itself create block-size-dependent policy.
EOF does not invent a model release. The replay resets support together with
the detector and includes support advancement in timed/allocation-guarded work.
Model inference cost and external host delivery remain separate, unverified
integration requirements.

The detector records eligible rapid-release decisions, warmup deferrals, model
vetoes, accepted/refused resets and later ordinary activations after a reset.
All changes are compiled under M3_OFFLINE_REPLAY_DIAGNOSTICS, default off.

## Inputs and one execution

Use the pinned ordinary and extended-middle recordings, labels, calibration
and spectral templates in the existing recovery corpus. CURRENT is spectral
lane collision ON, with all other experimental policies OFF: A4 440, trim -9,
sensitivity60, response75, max polyphony5, max fret24. No audio leaves the
authorized worker route. Model events already collected locally are:

- `adapted_cropped__ordinary-events.json`, SHA256
  `4e0601c42dbdccffe32c245a74ce80a9ae24be825f0b21e010b37f33f8ac9e92`
- `adapted_cropped__extended-middle-events.json`, SHA256
  `1eea72fdc62b0d2e1f09f871d3a0f1b6cf8b4490cb4413f7862fa42986f688e3`

One GitHub CPU job runs native tests, CURRENT/trial at blocks512/32/1024 on both
corpora, and scores saved snapshots and raw MIDI. Each arm/corpus has one
untimed block512 run with raw MIDI and timed companions at blocks32/1024/512:
16 replay invocations in total. No local native/audio/model
execution. Exact source/worker revisions and artifact IDs enter the dispatch
checkpoint. Small report collection once; bulk evidence stays remote unless
needed for a named diagnosis.

## Gates fixed before seeing the native result

Flag-off snapshot/raw MIDI must match the saved CURRENT references. Each arm
must preserve output across all three buffer sizes and timed/untraced output.
All processing allocation counts must be zero; block32 p99<=166666ns,
max<=333333ns, zero deadline overruns. Raw pairing must remain valid, with no
new stuck-note evidence or per-label retrigger growth. Holds use the budget below.

Report strict scoring and the user's prospective budget separately: each
label's present-time and longest-hold loss <=25ms AND <=5% of its own CURRENT
metric, with no newly completely missed label. Apply this budget separately
to pitch presence/longest presence and correct-lane held samples/longest hold.
Wrong-pitch, wrong-string and
gap outputs may not grow on either corpus; exact/all-expected pitch-set time
may not fall. Utility requires >=20% ordinary gap-output reduction, retaining
the prior latch's predeclared bar. Report pitch presence separately from
correct-string frame matches. Neither design recording is held-out evidence.

A failed clause rejects the screen; no threshold/predicate tuning or promotion
is authorized by success of the workflow. Installed plugin/defaults/scoreboard
remain unchanged. This tests whether a real state reset allows later normal
attacks to recover, not whether the detector knows physical note identity.
