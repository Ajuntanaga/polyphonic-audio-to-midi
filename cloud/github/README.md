# GitHub execution

GitHub Actions runs all new offloaded M3 processing. The laptop edits code,
collects small reports and sends ntfy updates. No native build or corpus replay
is needed locally.

The public source repository already runs native tests, VST3 packaging,
portable replay smoke checks and Linux configuration checks. Real recordings,
calibration and their detailed results stay in the private repository
`Ajuntanaga/m3-offload`. Its `corpus-20261108` release holds the compressed,
hashed recovery inputs. The workflow uses its own read-only `GITHUB_TOKEN`;
no Kaggle or ntfy credential is copied to GitHub.

`m3-offload.yml` is the canonical worker workflow. Copy it to
`.github/workflows/m3-offload.yml` in the private worker when changing it.
Dispatch it with a full pushed source commit and a specific task:

```bash
gh workflow run m3-offload.yml --repo Ajuntanaga/m3-offload \
  -f source_sha=FULL_COMMIT -f task=assignment-trace \
  -f dataset=physical-middle -f note=52
```

The assignment trace first records a fresh untraced OFF reference and then a
traced OFF replay using the same binary and inputs. It requires identical
outputs and unchanged labeled passages. Its report separates pitch selection
from string assignment; absent sampled rows are not missing MIDI counts.

`allocation-trace` runs physical-long OFF at block 32 once. Its diagnostic
build records C++ allocation caller addresses in fixed storage, then resolves
them after processing. It checks the complete replay hash against the retained
reference. Caller counts must account for every measured C++ allocation without
overflow. C and C++ hook counts overlap and must not be added together. The
instrumented timings cannot satisfy real-time acceptance; the ordinary build
keeps tracing off.

`core-check` runs the selected dataset OFF and ON at block 32 using the ordinary
build. Set `-f dataset=physical-high` to inspect the remaining failed timing gate,
or select another recording explicitly. The Python runner defaults to physical-long
when used without `--dataset`. Paired references come from the completed GitHub
corpus recovery, recorded in `docs/recovery/github-core-references-20261109.json`;
a missing pair stops the runner before native processing.
The scored pass retains its frequency reports; the timed pass detaches
their observer and skips optional subset/coherence report calculations.
Admission and unison state remain active, and explicitly enabled diagnostic
pruning retains the calculations it needs. The measurement scope identifies
this correction separately from older results that only detached the observer.
Both complete replay files must match their retained references, and timed
output must match scored output. The report checks allocations and timing
separately. This corrects the measurement scope; it does not imply a production
speed improvement or change installed output. A failed timing gate remains a
failed core check even when allocation and output checks pass.

`timing-diagnosis` runs that same bounded pair with the existing thread CPU
clock and slow-block state recorder enabled. It retains complete reference
identity checks, but its instrumented timing cannot pass native acceptance.
Phase counts locate periodic expensive work. CPU block statistics are usable
only when the measured clock resolution passes; coarse clocks cannot establish
whether a slow wall-clock block was processor work or a runner interruption.
The report distinguishes successful evidence collection from timing acceptance.

`corpus-recovery` recreates the full OFF/ON reference set. Start it only when
no equivalent recovery is active. Legacy Kaggle version 2 is complete and its
final outputs are collected: fourteen OFF references, one ON dataset, and no
passed native corpus gates. Do not poll or submit Kaggle work. Modal and Oracle
are unavailable.

`controlled-recovery` restores the ten held-out overlap controls from the
private `controls-pass2-20261109` release. Its three audio crops and calibration
match the retained historical hashes; the runner also checks every regenerated
mixture's sample hash before replay. These are independent plucks from the same
recording session, not new-session coverage. The original controls used
calibration without spectral templates, and this task preserves that setup.
The missing historical binary and feature sidecars are not reconstructed:
OFF/ON outputs have new source and binary provenance.

The first screen requires a positive target-note gain in the equal-level
nearby-note mixture, with no lost labels or increased false outputs across all
ten controls. Failure stops the task before buffer and timing work. A passing
screen proceeds to buffers 32 and 1024, requiring parity with 512 and both modes
to meet allocation and timing limits. Passing these controls alone does not
clear the separate corpus, live-host or MIDI lifecycle gates.

`controlled-timing-diagnosis` measures one retained octave control OFF
and ON at block 32, with CPU timing enabled. Select `-f control=octave_-12dB`
for the quiet-octave failure, or `octave_0dB` for the equal-level pair.
It uses the same private input
release and reconstruction checks, without spectral templates. Both complete
replay hashes must match `docs/recovery/github-activity-scan-controls-20261109.json`.
The pair has a six-minute processing cap, with at most three minutes per mode.
This diagnosis cannot replace the failed native timing result or pass acceptance;
it investigates CPU work versus elapsed-time delays without repeating the full
control sweep. The dataset and note dispatch inputs are unused for this task.

Runs are manual and serialized. The trace has a 60-minute job cap; full
recovery has a 210-minute cap, including compilation. These are standard CPU
runners using the account's GitHub Actions allowance, not a GPU service.
Reports and failure logs last 14 days; compressed traces, references and the
replay binary last 7 days. Collect useful evidence before expiry. Input release
assets persist separately. This setup does not change account billing settings.

Record the exact worker repository, run ID, source commit, artifact names and
local output path under `portable_compute.github_worker` in
`build/modal/current-status.json`. The existing ten-minute heartbeat follows
those runs, collects small completed reports and sends one inline ntfy summary
under 4,000 UTF-8 bytes. It does not dispatch work. Only explicit confirmed
receipts replace the latest successful notification receipt; ambiguous sends
are not retried.

New measurements remain offline evidence. Preserve installed scores and
default-off behavior until label/error, allocation, buffer, timing, host and
MIDI lifecycle gates pass. Successful compilation or a completed cloud job
alone does not establish reliable live use.
