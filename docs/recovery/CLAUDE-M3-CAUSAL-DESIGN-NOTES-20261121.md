# Claude: why the causal gap exists, a runner review, and pre-registered bridge expectations — 2026-11-21

Sources: Codex's `tools/basic_pitch_streaming.py` (read in full), and the upstream files `note_creation.py` and `inference.py` at the pinned commit `fa5997af…`, read as raw text by a subagent (no local install, no inference, no download, no dispatch). Line numbers were not available from the fetch; the quoted behaviour is verbatim-checked, the line positions are not.

## 1. What upstream does at note boundaries

- **Start = onset-peak frame.** Candidates are strict local maxima in time of the onset activation (`argrelmax`) at or above `onset_thresh`, after `infer_onsets` has taken the element-wise max of the onsets and a rescaled 2-frame rise of the note activation. The note starts at that frame whether or not the note activation is above `frame_thresh` there; the threshold only governs the end. A strict local maximum already needs the next frame.
- **End = last above-threshold frame.** From the start the walk runs forward and stops after `energy_tol = 11` consecutive sub-threshold frames, then steps back to the last above-threshold frame. A dip of up to 10 frames (116 ms) inside a note is bridged.
- **Minimum length filter.** `minimum_note_length` 127.7 ms becomes 11 frames; a note with `end − start <= 11` is dropped. A surviving note therefore has at least 12 frames after its start, so its start is only knowable about 139 ms later, plus the model's own right context.
- **Melodia.** Seeds on the global maximum of the remaining energy, then extends backward and forward with the same 11-frame tolerance, with no onset gating, so it can start a note before any onset.

## 2. What this implies (descriptive, not tested)

1. Offline onsets are retroactive. A first-present delay of 0 ms on about half of the offline labels is the expected result of onset-peak placement plus backward extension, not an anomaly, and no causal emitter can reproduce it in real time. Together with the 72.7/84.35 ms right context this is the structural source of the +106.6 ms median shift; the timestamp convention contributes at most ~10 ms (`CLAUDE-M3-OFFLINE-CLOCK-DRIFT-CHECK-20261121.md`).
2. The 41 two-piece splits fit a release-rule difference: the forward decoder ends a note after 3 consecutive sub-threshold frames, upstream after 11. A causal analogue with upstream's own constant would be `release_frames = 11` (cost: every `off` is 8 frames, 93 ms, later, which moves extra voice-samples into gaps and has to be reported). This is a hypothesis for the bridge to test, not a proposal to change the frozen decoder.
3. The forward start rule differs from upstream in two ways: it needs `note >= 0.3` at the onset frame, and `onset >= 0.5` rather than a peak. When the onset peak precedes the note crossing by a frame or two, it falls back to three consecutive frames, which adds up to about 23 ms on top of the context lag.

## 3. Review of the runner (no bug found)

- Frame `f` is model sample `f × 256`; each call consumes frames 164 and 165, so right context is 84.35 ms for even frames and 72.74 ms for odd frames, delivered together. The even frame could have been read a call earlier at window position 166 (61.1 ms), so the fixed readout position is a design choice, not a constraint of the model.
- The resampler applies no delay compensation: the 12,801-tap FIR has a group delay of 6,400 up-rate samples = 43.5 source samples = 0.45 ms. Negligible, but it shifts the nominal clock slightly.
- The decoder allows re-activation after a release (docstring says no retrigger while active, consistent). Event pairing, EOF clipping and the FIFO clock read correctly to me.
- The 164/165 readout means 170 of every 172 computed frames are discarded; fine for feasibility, relevant for any later cost argument.

## 4. Expectations I am writing down before the bridge result

On the saved tape (frames 164/165 only, ordinary recording):
- D0 reproduces 1,192 events and 18,583,289 present, or the tape is not the decoder's input.
- D1 (raw `note >= 0.3`) has at least as many segments as D0 and no fewer dropouts than D0 on labels where the attack rule is what failed.
- If D2 (upstream decode on the tape's frames) stays far below 67.5% nominal-clock coverage, the loss is readout (context, normalisation, resampler); if it lands within a few points, the loss is the causal decoder. If a release of 11 frames merges most of the 41 splits at a modest extra-voice cost, the splits are the release rule.
- I do not expect the 18 dropouts to be rescued by the decoder alone (offline presence on them is 139–643 ms and zero under compute-free replay).

## 5. Two follow-ups after the bridge, neither dispatched, neither relaxing a gate

- **Latency-compensated diagnostic (events only, no new inference).** Re-score the same emitted spans shifted earlier by a fixed design constant (72.74 or 84.35 ms, the readout's own right context, not fitted per label), reported next to the primary score. It answers how much of the coverage gap is declared-latency rather than content, and whether any plugin-reported latency could in principle buy it back. Host handling of MIDI output latency is unverified, so this stays diagnostic. It needs the 166 KB `ordinary-events.json` from the remote bulk artifact.
- **Right-context curve (one new frozen job).** The same pass with readout at a small fixed set of window positions (for example 164/165 as now, 156/157, 148/149, 140/141), same decoder, same gate, reported as a curve of coverage, per-label loss and false output against context. Caveat to state up front: the whole corpus is one 111 s recording, so any choice made from this curve is tuned on its own evaluation file; the curve is a design characterization, and a choice needs a held-out recording first.
