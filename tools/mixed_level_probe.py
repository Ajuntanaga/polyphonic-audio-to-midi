"""Synthetic mixed-level probe windows for the pinned Basic Pitch graphs.  Pure numpy; no model, no recording, no weights.

Plan, definitions, predictions and reading rules: docs/recovery/CLAUDE-M3-MIXED-LEVEL-PROPOSAL-20261122.md.  Every window is one model input
(43844 samples at 22050 Hz).  A tone's level is the root-sum-square amplitude of its harmonics in dB re full scale, the same quantity the
registered audio-level read measured on the corpus (tools/audio_release_levels.py), so a probe level of -50 dB is comparable with a corpus `pre` of
-50 dB.  The runner (tools/portable_mixed_level_probe.py) feeds the windows to the models; nothing here touches onnx or onnxruntime.
"""
import hashlib

import numpy as np

from tools.audio_release_levels import fundamental, harmonic_numbers

RATE = 22050
SAMPLES = 43844
FRAME_HOP = 256
FIRST_MIDI = 21
BINS = 88
FRAMES = 172
READOUT = (164, 165)
PROFILE = (150, 172)
CUT = READOUT[0] * FRAME_HOP          # 41984: the probe stops at the nominal time of readout frame 164
ENDED = 22050                         # an "ended" companion is gone 1.0 s into the window, 0.9 s before readout frame 164
FADE = 441                            # 20 ms raised-cosine fade-out of an ended companion
ATTACK = 221                          # 10 ms raised-cosine attack at the start of every tone
ACTIVE = 0.3                          # decoder frame threshold, descriptive only
COMPANION_MIDI = 43
GOLDEN = 0.6180339887498949
NOISE_SEED = 20261122
DITHER_DB = -96.0                     # RMS of the white-noise floor, dB re full scale
NEAR = 2                              # semitones around the probe (and the companion) excluded from `other_max`


def tone(midi, level_db, role, n=SAMPLES, rate=RATE):
    """Harmonics 1..4 of `midi` (those at or below 2 kHz, as in the audio-level read), amplitude 1/k, level_db = root-sum-square amplitude."""
    harmonics = harmonic_numbers(midi)
    base = 10.0 ** (level_db / 20.0) / np.sqrt(sum(1.0 / k ** 2 for k in harmonics))
    t = np.arange(n) / rate
    f0 = fundamental(midi)
    x = np.zeros(n)
    for k in harmonics:
        phase = 2.0 * np.pi * ((GOLDEN * k + 0.31 * role) % 1.0)
        x += base / k * np.sin(2.0 * np.pi * k * f0 * t + phase)
    return x


def sustained(n=SAMPLES):
    envelope = np.ones(n)
    ramp = np.arange(ATTACK)
    envelope[:ATTACK] = 0.5 - 0.5 * np.cos(np.pi * ramp / ATTACK)
    return envelope


def cut_envelope(n=SAMPLES):
    envelope = sustained(n)
    envelope[CUT:] = 0.0
    return envelope


def ended_envelope(n=SAMPLES):
    envelope = sustained(n)
    envelope[ENDED:] = 0.0
    envelope[ENDED - FADE:ENDED] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(FADE) / FADE)
    return envelope


def noise_floor():
    return np.random.default_rng(NOISE_SEED).standard_normal(SAMPLES) * 10.0 ** (DITHER_DB / 20.0)


def make_window(floor, probe=None, companion=None):
    """floor 'zero' (exact zeros wherever nothing sounds) or 'dither' (a white-noise floor everywhere); probe (midi, level, form); companion (level, timing)."""
    if floor not in ('zero', 'dither'):
        raise ValueError('Unknown floor: ' + str(floor))
    x = np.zeros(SAMPLES)
    if probe is not None:
        midi, level, form = probe
        if form not in ('sustained', 'cut'):
            raise ValueError('Unknown probe form: ' + str(form))
        x += tone(midi, level, 0) * (cut_envelope() if form == 'cut' else sustained())
    if companion is not None:
        level, timing = companion
        if timing not in ('through', 'ended'):
            raise ValueError('Unknown companion timing: ' + str(timing))
        x += tone(COMPANION_MIDI, level, 1) * (ended_envelope() if timing == 'ended' else sustained())
    if floor == 'dither':
        x += noise_floor()
    return x.astype(np.float32)


def window_id(floor, form, midi, level, companion=None):
    """companion None or (timing, delta)."""
    suffix = 'none' if companion is None else '%s+%d' % companion
    return '%s|%s|m%d|L%d|%s' % (floor, form, midi, level, suffix)


def reference_id(floor, kind, timing=None, level=None):
    return '%s|ref|silence' % floor if kind == 'silence' else '%s|ref|%s|C%d' % (floor, timing, level)


def build_windows(spec):
    """Every probe window in a fixed order, with its samples; companion levels above `companion_cap` are never generated."""
    p = spec['probe']
    windows = []
    for floor in p['floors']:
        windows.append(dict(id=reference_id(floor, 'silence'), kind='silence', floor=floor,
                            samples=make_window(floor)))
        for timing in p['timings']:
            for level in p['reference_companion_levels']:
                windows.append(dict(id=reference_id(floor, 'companion_only', timing, level), kind='companion_only',
                                    floor=floor, companion=dict(timing=timing, level=level),
                                    samples=make_window(floor, companion=(level, timing))))
        for form in p['forms']:
            for midi in p['pitches']:
                for level in p['levels']:
                    windows.append(dict(id=window_id(floor, form, midi, level), kind='probe', floor=floor, form=form,
                                        midi=midi, level=level, companion=None,
                                        samples=make_window(floor, probe=(midi, level, form))))
                    for timing in p['timings']:
                        for delta in p['deltas']:
                            companion_level = level + delta
                            if companion_level > p['companion_cap']:
                                continue
                            windows.append(dict(
                                id=window_id(floor, form, midi, level, (timing, delta)), kind='probe', floor=floor,
                                form=form, midi=midi, level=level,
                                companion=dict(timing=timing, delta=delta, level=companion_level),
                                samples=make_window(floor, probe=(midi, level, form), companion=(companion_level, timing))))
    ids = [w['id'] for w in windows]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate window ids')
    return windows


def windows_digest(windows):
    h = hashlib.sha256()
    for w in windows:
        h.update(w['id'].encode() + b'\0')
        h.update(np.ascontiguousarray(w['samples'], dtype='<f4').tobytes())
    return h.hexdigest()


def extract(meta, note, onset, minimum, range_):
    """One record from a window's frame posteriors ([172, 88] note and onset) and the two exposed normalization scalars.
    Frontend values and note decisions are separate fields; nothing is thresholded except the descriptive `active_bins`."""
    note, onset = np.asarray(note), np.asarray(onset)
    if note.shape != (FRAMES, BINS) or onset.shape != (FRAMES, BINS):
        raise ValueError('Unexpected output shape')
    first, second = READOUT
    record = dict(id=meta['id'], min_db=float(minimum), range_db=float(range_),
                  max_note=float(max(note[first].max(), note[second].max())),
                  active_bins=int(((note[first] >= ACTIVE) | (note[second] >= ACTIVE)).sum()))
    excluded = np.zeros(BINS, dtype=bool)
    if meta['kind'] == 'probe':
        p = meta['midi'] - FIRST_MIDI
        record['note_probe'] = [float(note[first, p]), float(note[second, p])]
        record['onset_probe'] = [float(onset[first, p]), float(onset[second, p])]
        record['response'] = max(record['note_probe'])
        record['profile'] = [float(v) for v in note[PROFILE[0]:PROFILE[1], p]]
        excluded[max(0, p - NEAR):p + NEAR + 1] = True
    if meta['kind'] != 'silence' and meta.get('companion') is not None:
        q = COMPANION_MIDI - FIRST_MIDI
        record['note_companion'] = [float(note[first, q]), float(note[second, q])]
        excluded[max(0, q - NEAR):q + NEAR + 1] = True
    rest = np.where(excluded, -1.0, np.maximum(note[first], note[second]))
    record['other_max'] = float(rest.max())
    return record


def run_windows(windows, run_stats, run_plain):
    """`run_stats(samples)` -> (note, onset, min, range) from the graph that also exposes the normalization scalars; `run_plain(samples)` ->
    (note, onset) from the unmodified graph.  The two must agree exactly; the difference is recorded per window."""
    records = []
    for meta in windows:
        note, onset, minimum, range_ = run_stats(meta['samples'])
        plain_note, plain_onset = run_plain(meta['samples'])
        record = extract(meta, note, onset, minimum, range_)
        record['plain_max_abs_note'] = float(np.abs(np.asarray(note) - np.asarray(plain_note)).max())
        record['plain_max_abs_onset'] = float(np.abs(np.asarray(onset) - np.asarray(plain_onset)).max())
        records.append(record)
    return records


def identity(records, tolerance):
    worst = max(max(r['plain_max_abs_note'], r['plain_max_abs_onset']) for r in records)
    return dict(max_abs_difference=worst, tolerance=tolerance, passed=bool(worst <= tolerance), windows=len(records))
