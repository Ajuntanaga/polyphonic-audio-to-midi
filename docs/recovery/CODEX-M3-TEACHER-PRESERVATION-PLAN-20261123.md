# Fixed original-model preservation experiment

Codex owns the new `basic_pitch_teacher_adaptation` helpers, portable runner,
tests, specification and worker workflow. Claude remains an equal peer and can
continue the independent ordinary58 acoustic work. No existing native or
installed model is changed. This note is the coordination record before coding
or inference; no acknowledgement or further permission is needed under the
user's standing CPU-job authorization.

## Why this change

The original guitar fit and the later boundary fit gained labeled notes while
adding false output and losing some source occurrences. Both optimized only
note-label BCE. The preservation objective explicitly deferred in
`CODEX-M3-ADAPTATION-NEXT-QUESTION-20261122.md` has not been tested. It can constrain
output drift; it cannot supply missing acoustic labels or establish re-pluck
safety. The original model can also be wrong, so preserving it can prevent a
useful gain. That is a measured risk, not a reason to adjust the loss afterward.

## Frozen intervention

Start from the same pinned original Spotify model. Use the exact original
4096 training, 1024 calibration and 1024 test windows from all 555 takes.
Keep both epochs, optimizer, shuffle, batch size, waveform gains and labels.
No new boundary views, exclusions, decoder, normalization or cutoff changes.
Before the first update, cache the original model's note and onset probabilities
for every training window. These are immutable targets, outside the gradient
graph. Optimize the sum of three equally weighted means over all 172x88 bins:

1. BCE(student note, intended note label).
2. Bernoulli KL(original note || student note).
3. Bernoulli KL(original onset || student onset).

Clip each probability to [1e-7, 1-1e-7] for logarithms. Coefficients are all 1,
fixed before data. No temperature, sweep, selection, early stopping or retry.
Original onset outputs are soft preservation targets, not acoustic onset labels.
Only the final second-epoch checkpoint is the candidate.

## One bounded first-stage job

GitHub CPU only, one fit. Score original, the already saved original-BCE epoch2,
and the new epoch2 on every unchanged role window. Keep all per-occurrence
present/longest deltas and probabilities remotely. Report note/onset probability
drift, threshold crossings, exact sets, extras and silence extras. Verify source
and plan pins, original restoration and immutable teacher-cache hashes. The
prior rejected fit is a comparator, never a new acceptance reference.

Freeze the window advancement decision now: complete integrity; test recall gain
at least 5 percentage points versus original; and, on each of train/calibration/
test, no extra-note or silence-extra growth, no loss of exact frames, no newly
missed source occurrence, and each occurrence's present and longest loss within
BOTH 25 ms and 5% of its own original value. Convert the 25 ms limit using the
nominal 256/22050-second model frame, without rounding the allowance upward.
Report the older zero-loss clause separately. Report the unchanged absolute
representation targets (train precision 99%, others 95%; recall 80%, exact-set
70%, overall and 3/4/5 pitches; zero silence extras) separately, too.

Passing advancement only warrants a subsequent continuous-recording comparison;
it is not model acceptance. Failing it closes this exact setting, without tuning.
This job contains no export, continuous replay, native execution or host test.
It avoids spending those stages on a window-rejected candidate. A pass still
needs continuous per-label budget/extras gates, backend identity, timing,
independent data and host/device checks. Installed scores remain unchanged.

These roles share an instrument/session and have been examined previously;
they are not a new blind validation. Constructed nominal-frame pitch occupancy
is distinct from tuner string matches and delivered MIDI. No claim about equal
pitch unison multiplicity, bends or genuine re-plucks follows from this job.
