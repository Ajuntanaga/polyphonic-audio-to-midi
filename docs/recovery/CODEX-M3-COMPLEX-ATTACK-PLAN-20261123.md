# A dedicated attack detector on the frozen repeat controls

Status: implementation claimed by Codex, before any new audio result. Claude's
ordinary acoustic attack-zone work is separate. This uses the standing scoped
CPU-job authorization; no installed change or promotion.

The existing M3 onset is a short energy-rise value used by the string posterior.
Remembering it would also protect known lane flicker. The next experiment is a
standalone, established attack detector, not another threshold on that value.

Use aubio **0.4.9 complex-domain onset**, one configuration: FFT 2048, hop 512,
96 kHz (21.33 ms / 5.33 ms). The window/hop are our frozen engineering choice,
not the upstream demo defaults. Keep the library's complex-method defaults:
threshold 0.15, minimum inter-onset interval 50 ms, silence -70 dB, whitening on,
compression 1. No resampling, trim, normalization, threshold or window sweep.
The six exact WAVs already retained in run **45155740922** are the only audio.
Fetch them on GitHub; do not reconstruct them or replay M3 again.

Primary clock is the exclusive end of the hop needed to return the cue.
aubio's `get_last()` subtracts an internal delay; report it separately and never
use it as delivery time. Actual call durations are descriptive CPU measurements,
not a live-host deadline pass. Zero-pad only the final partial hop, expose the
padding count, and include any cue there in the extra-cue count.

Before scoring, require archive/member hashes, six waveform sizes/rates, finite
mono samples, package/configuration identity, and identical cues in each repeated
fixture's unchanged prefix versus its single-copy control. Score one fixed rule:

- Every single-copy fixture has exactly one cue, after the insertion and by the
  saved first per-voice NoteOn; no later cues across the whole fixture.
- Every repeated fixture has exactly two cues: the first satisfies the same
  bound; the second is after its insertion and no later than the saved first
  extra per-voice NoteOn. Report both overlap and separated copies.
- All six must pass to support this bounded cue. Failure rejects this setting;
  no retry or parameter tuning. Report every cue and deadline regardless.

Markers are approximate rise landmarks; these are copied waveform responses,
not verified new physical plucks. This is a global onset cue on one-pitch
fixtures. Even a pass cannot assign chord attacks to pitches, establish ordinary
re-pluck preservation, or justify suppressing production MIDI events.

Files claimed: `tools/complex_attack_baseline.py`,
`tools/portable_complex_attack_baseline.py`, its synthetic contract test,
`complex-attack-baseline-20261123.json`, this note/checkpoint/result, and worker
`m3-complex-attack-baseline.yml`. Native source and Claude files are unclaimed.
Small report collected once; waveform evidence stays remote.

Primary sources: [Duxbury et al., DAFx 2003](https://www.dafx.de/paper-archive/2003/pdfs/dafx81.pdf)
describes phase/amplitude prediction in the complex domain;
[aubio 0.4.9 onset implementation](https://raw.githubusercontent.com/aubio/aubio/0.4.9/src/onset/onset.c)
defines the fixed peak-picking defaults and backdated timestamp. Use the
GPL-licensed package solely as a separate benchmark; no upstream implementation
is copied into the plugin.
