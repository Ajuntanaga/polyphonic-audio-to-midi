"""Synthetic release probe: does a model hold a note longer after an abrupt end or on a smooth decay?

Pure numpy; no model or recording I/O here (the runner is tools.portable_basic_pitch_release_probe).  Treatments, definitions and
predictions P0-P3 are fixed in docs/recovery/CLAUDE-M3-RELEASE-PROBE-TREATMENTS-20261122.md and
docs/recovery/CLAUDE-M3-RELEASE-PROBE-PROPOSAL-20261122.md, written before any run.  Not a fit, a gate or a guitar-quality benchmark.
"""
import math

import numpy as np

from tools.basic_pitch_streaming import SETTINGS

RATE = SETTINGS['model_rate']
SAMPLES = SETTINGS['model_samples']
FRAMES = SETTINGS['model_frames']
HOP = SETTINGS['frame_hop']
FIRST_MIDI = SETTINGS['first_midi_note']
THRESHOLD = SETTINGS['frame_threshold']
RELEASE_FRAMES = SETTINGS['release_frames']

ONSET = 4000
END = 20000
TAPER = 110
STEADY_RMS = 0.05
HARMONICS = 6
PITCHES = (45, 52, 59, 66)
TAUS = (0.05, 0.1, 0.2, 0.4)
LAST_STEADY_FRAME = (END - 1) // HOP
ACTIVE_FRAMES = (LAST_STEADY_FRAME - 3, LAST_STEADY_FRAME)
DB_PER_NEPER = 20 / math.log(10)

P0_MAX_MS = 25.0
P1_MIN_DB = 3.0
P1_TAUS = (0.1, 0.2, 0.4)
P2_TAU = 0.2
P2_MIN_MS = 30.0
P3_MAX_DB = 3.0
P3_PITCHES = (52, 59)


def case_key(kind, tau=None):
    return kind if tau is None else '%s_%s' % (kind, tau)


def all_cases():
    """(key, kind, tau) for every signal: the abrupt end and four decays per pitch, plus the sustained and silence controls."""
    return ([('abrupt', 'abrupt', None)] + [(case_key('decay', tau), 'decay', tau) for tau in TAUS]
            + [('sustained', 'sustained', None), ('silence', 'silence', None)])


def tone(midi):
    clock = np.arange(SAMPLES, dtype=np.float64) / RATE
    frequency = 440.0 * 2.0 ** ((midi - 69) / 12.0)
    signal = np.zeros(SAMPLES, dtype=np.float64)
    for harmonic in range(1, HARMONICS + 1):
        signal += np.sin(2 * np.pi * frequency * harmonic * clock) / harmonic
    return signal


def envelope(kind, tau=None):
    env = np.zeros(SAMPLES, dtype=np.float64)
    ramp = np.linspace(0, 1, TAPER, endpoint=True)
    if kind == 'silence':
        return env
    if kind == 'sustained':
        env[ONSET:] = 1.0
        env[ONSET:ONSET + TAPER] = ramp
        return env
    env[ONSET:END] = 1.0
    env[ONSET:ONSET + TAPER] = ramp
    if kind == 'abrupt':
        env[END - TAPER:END] = ramp[::-1]
    elif kind == 'decay':
        n = np.arange(END, SAMPLES, dtype=np.float64)
        env[END:] = np.exp(-(n - END) / (tau * RATE))
    else:
        raise ValueError('Unknown case ' + kind)
    return env


def render(midi, kind, tau=None):
    """float32 window of SAMPLES; the tone's raw RMS over the steady segment [ONSET, END) is STEADY_RMS."""
    env = envelope(kind, tau)
    if kind == 'silence':
        return env.astype(np.float32)
    raw = tone(midi)
    rms = math.sqrt(float(np.mean(raw[ONSET:END] ** 2)))
    return (raw * (STEADY_RMS / rms) * env).astype(np.float32)


def level_db(tau, frame):
    """Envelope level of a decay at a frame, dB relative to the steady level (negative)."""
    return -DB_PER_NEPER * (HOP * frame - END) / (tau * RATE)


def delay_ms(frame):
    return (HOP * frame - END) * 1000.0 / RATE


def measure(note, midi, tau=None):
    """note: (FRAMES, 88) probabilities.  Active, release frame, delay, level; censored values are bounds (see the treatments note)."""
    column = np.asarray(note, dtype=np.float64)[:, midi - FIRST_MIDI]
    low, high = ACTIVE_FRAMES
    active = bool(np.all(column[low:high + 1] >= THRESHOLD))
    out = dict(midi=midi, active=active)
    if not active:
        return out
    release = next((f for f in range(LAST_STEADY_FRAME + 1, FRAMES) if column[f] < THRESHOLD), None)
    censored = release is None
    frame = FRAMES - 1 if censored else release
    run, off = 0, None
    for f in range(LAST_STEADY_FRAME + 1, FRAMES):
        run = run + 1 if column[f] < THRESHOLD else 0
        if run >= RELEASE_FRAMES:
            off = f
            break
    out.update(release_frame=None if censored else release, censored=censored, delay_ms=round(delay_ms(frame), 3),
               edge_affected=bool(not censored and release >= SETTINGS['readout_frames'][1]), decoder_off_frame=off)
    if tau is not None:
        out['level_db'] = round(level_db(tau, frame), 3)
    return out


def _both_active(results, midi, key):
    a, b = results['adapted'][key].get(midi), results['unmodified'][key].get(midi)
    return (a, b) if a and b and a['active'] and b['active'] else None


def _delay_exceeds(adapted, original, margin):
    """adapted delay - original delay >= margin, proven by the bounds: the original must be uncensored; the adapted may be a lower bound."""
    return (not original['censored']) and adapted['delay_ms'] - original['delay_ms'] >= margin


def _level_lower(adapted, original, margin):
    """adapted release level <= original level - margin, proven by the bounds (original uncensored; adapted bound counts)."""
    return (not original['censored']) and adapted['level_db'] <= original['level_db'] - margin


def verdicts(results):
    """results[model][case_key][midi] = measure(...) for model in unmodified/adapted.  Returns P0-P3 with the evaluability rules of the
    treatments note: a prediction is evaluable only if at least 3 pitches can be compared, and only a bound that proves a statement confirms it."""
    out = {}

    pairs = {m: _both_active(results, m, 'abrupt') for m in PITCHES}
    usable = {m: p for m, p in pairs.items() if p}
    if len(usable) < 3:
        out['P0'] = dict(verdict='unevaluable', evaluable_pitches=sorted(usable))
    else:
        rows = {m: dict(difference_ms=round(a['delay_ms'] - b['delay_ms'], 3), both_uncensored=not a['censored'] and not b['censored'])
                for m, (a, b) in usable.items()}
        ok = all(r['both_uncensored'] and abs(r['difference_ms']) <= P0_MAX_MS for r in rows.values())
        out['P0'] = dict(verdict='pass' if ok else 'miss', evaluable_pitches=sorted(usable), by_pitch=rows)

    counts, evaluable, detail = 0, 0, {}
    for m in PITCHES:
        usable_taus = [t for t in P1_TAUS if _both_active(results, m, case_key('decay', t))]
        if len(usable_taus) < 2:
            continue
        evaluable += 1
        proven = [t for t in usable_taus
                  if _level_lower(*_both_active(results, m, case_key('decay', t)), P1_MIN_DB)]
        detail[m] = dict(taus_compared=usable_taus, taus_proven=proven, counts=len(proven) >= 2)
        counts += len(proven) >= 2
    if evaluable < 3:
        out['P1'] = dict(verdict='unevaluable', evaluable_pitches=evaluable, by_pitch=detail)
    else:
        out['P1'] = dict(verdict='pass' if counts >= 3 else 'miss', pitches_counted=counts, evaluable_pitches=evaluable, by_pitch=detail)

    if out['P1']['verdict'] != 'pass':
        out['P2'] = dict(verdict='not_evaluated', reason='P1 is not a pass')
    else:
        key = case_key('decay', P2_TAU)
        usable2 = {m: _both_active(results, m, key) for m in PITCHES if _both_active(results, m, key)}
        if len(usable2) < 3:
            out['P2'] = dict(verdict='unevaluable', evaluable_pitches=sorted(usable2))
        else:
            proven = [m for m, (a, b) in usable2.items() if _delay_exceeds(a, b, P2_MIN_MS)]
            out['P2'] = dict(verdict='pass' if len(proven) >= 3 else 'miss', evaluable_pitches=sorted(usable2), pitches_proven=sorted(proven),
                             difference_ms={m: round(a['delay_ms'] - b['delay_ms'], 3) for m, (a, b) in usable2.items()})

    per_model, enough, holds = {}, True, True
    for model in ('unmodified', 'adapted'):
        rows = {}
        for tau in TAUS:
            key = case_key('decay', tau)
            low, high = (results[model][key].get(m) for m in P3_PITCHES)
            if low and high and low['active'] and high['active'] and not low['censored'] and not high['censored']:
                rows[tau] = round(low['level_db'] - high['level_db'], 3)
        per_model[model] = rows
        enough = enough and len(rows) >= 2
        holds = holds and all(abs(v) <= P3_MAX_DB for v in rows.values())
    out['P3'] = dict(verdict='unevaluable' if not enough else ('pass' if holds else 'miss'), level_difference_db_52_minus_59=per_model)
    return out
