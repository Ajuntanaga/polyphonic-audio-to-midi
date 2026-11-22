"""Frozen window planner and scoring for one pretrained note-adaptation screen.

These helpers have no file, model or recorded-audio access. The portable runner
does those operations on GitHub. A window is an offline training example, not
a claim that its labels or model predictions are available causally.
"""
from collections import Counter, defaultdict

import numpy as np


SETTINGS = dict(model_rate=22050, input_samples=43844, frames=172, frame_hop=256,
    first_note=21, notes=88, source_rate=96000, resample_up=147, resample_down=640,
    train_examples=4096, calibration_examples=1024, test_examples=1024,
    train_seed=2026112201, calibration_seed=2026112202, test_seed=2026112203,
    component_gains_db=[0, -6, -12, -18, -24], mixture_gains_db=[-12, -6, 0, 6],
    component_rms=0.05, normalization_floor=1e-12, edge_taper_samples=110,
    silence_every=20, max_components=5, cutoff=0.3,
    batch_size=4, epochs=2, learning_rate=0.0001, clip_global_norm=1.0,
    optimizer='Adam', beta_1=0.9, beta_2=0.999, epsilon=1e-7, shuffle_seed=2026112204)


def resampled_length(source_samples):
    return (int(source_samples)*SETTINGS['resample_up']+SETTINGS['resample_down']-1)//SETTINGS['resample_down']


def window_plan(takes, role, count, seed):
    """Anchor every retained take as a singleton, then draw distinct strings.

    Short excerpts are placed in a zero window without repetition/stretching.
    Long excerpts supply a uniformly chosen full window. Every placement and
    crop is fixed before audio or model outputs are inspected.
    """
    sources = [take for take in takes if take['role'] == role]
    groups = defaultdict(list)
    for take in sources:
        groups[take['string_mask']].append(take)
    if len(groups) < SETTINGS['max_components'] or count-count//20-1 < len(sources):
        raise ValueError('Insufficient strings or examples to retain every take')
    rng, anchored, result = np.random.default_rng(seed), 0, []
    for i in range(count):
        row = dict(example=i, role=role, gain_db=0, components=[])
        if i % SETTINGS['silence_every'] == 0:
            result.append(row)
            continue
        is_anchor = anchored < len(sources)
        anchor = sources[anchored] if is_anchor else sources[int(rng.integers(len(sources)))]
        anchored += 1
        n = 1 if is_anchor else int(rng.integers(1, SETTINGS['max_components']+1))
        others = sorted(set(groups)-{anchor['string_mask']})
        strings = rng.choice(others, n-1, replace=False).tolist()
        chosen = [anchor]+[groups[s][int(rng.integers(len(groups[s])))] for s in strings]
        row['gain_db'] = int(rng.choice(SETTINGS['mixture_gains_db']))
        row['anchored_singleton'] = is_anchor
        for take in chosen:
            available = resampled_length(take['end_sample']-take['start_sample'])
            length = min(available, SETTINGS['input_samples'])
            crop = int(rng.integers(available-length+1))
            placement = int(rng.integers(SETTINGS['input_samples']-length+1))
            row['components'].append(dict(source_key=take['key'], note=take['midi_note'],
                string_mask=take['string_mask'], crop_begin=crop, length=length,
                placement=placement, gain_db=int(rng.choice(SETTINGS['component_gains_db']))))
        result.append(row)
    if {c['source_key'] for row in result for c in row['components']} != {t['key'] for t in sources}:
        raise ValueError('Source role coverage differs')
    return result


def component_frames(component):
    points = np.arange(SETTINGS['frames'])*SETTINGS['frame_hop']
    return (points >= component['placement']) & (points < component['placement']+component['length'])


def render_window(row, clips):
    signal = np.zeros(SETTINGS['input_samples'], np.float64)
    labels = np.zeros((SETTINGS['frames'], SETTINGS['notes']), bool)
    levels = []
    for component in row['components']:
        begin, length = component['crop_begin'], component['length']
        clip = np.asarray(clips[component['source_key']][begin:begin+length], np.float64).copy()
        if clip.shape != (length,) or not np.isfinite(clip).all() or length <= 0:
            raise ValueError('Invalid source crop')
        rms = float(np.sqrt(np.mean(clip*clip)))
        # Fade only the artificial crop boundaries; do not remove their labels.
        taper = min(SETTINGS['edge_taper_samples'], length//2)
        ramp = np.linspace(0, 1, taper, endpoint=True)
        if taper:
            clip[:taper] *= ramp
            clip[-taper:] *= ramp[::-1]
        gain = SETTINGS['component_rms']/max(rms, SETTINGS['normalization_floor'])
        gain *= 10**(component['gain_db']/20)
        left = component['placement']
        signal[left:left+length] += clip*gain
        col = component['note']-SETTINGS['first_note']
        if not 0 <= col < SETTINGS['notes']:
            raise ValueError('Source note outside model output')
        labels[component_frames(component), col] = True
        levels.append(dict(source_key=component['source_key'], crop_rms=rms,
                           normalization_gain=gain))
    signal *= 10**(row['gain_db']/20)
    if not np.isfinite(signal).all():
        raise ValueError('Nonfinite rendered window')
    return signal.astype(np.float32), labels, levels


def frame_summary(probability, targets):
    p, y = np.asarray(probability), np.asarray(targets, bool)
    if p.shape != y.shape or p.ndim != 3 or p.shape[1:] != (172, 88) or not np.isfinite(p).all():
        raise ValueError('Invalid note prediction tape')
    if np.any((p < 0) | (p > 1)):
        raise ValueError('Invalid probabilities')
    prediction = p.reshape(-1, 88) >= SETTINGS['cutoff']
    truth = y.reshape(-1, 88)
    def count(mask):
        t, g = truth[mask], prediction[mask]
        tp, fp, fn = int((t & g).sum()), int((~t & g).sum()), int((t & ~g).sum())
        return dict(frames=len(t), expected_note_frames=tp+fn, found_note_frames=tp,
            extra_note_frames=fp, missing_note_frames=fn, exact_frames=int(np.all(t == g, axis=1).sum()),
            precision_percent=100*tp/(tp+fp) if tp+fp else None,
            recall_percent=100*tp/(tp+fn) if tp+fn else None,
            exact_set_percent=100*float(np.all(t == g, axis=1).mean()) if len(t) else None)
    return dict(overall=count(np.ones(len(truth), bool)),
        by_pitch_count={str(n): count(truth.sum(axis=1) == n) for n in range(6)},
        silence_extra_note_frames=int(prediction[~truth.any(axis=1)].sum()),
        unit='Nominal model-frame distinct-pitch occupancy in constructed training windows; not tuner/string matches or delivered MIDI')


def representation_gate(summary, precision):
    rows = [summary['overall']]+[summary['by_pitch_count'][str(n)] for n in (3, 4, 5)]
    return all(row['frames'] > 0 and row['precision_percent'] is not None
               and row['precision_percent'] >= precision and row['recall_percent'] >= 80
               and row['exact_set_percent'] >= 70 for row in rows) and summary['silence_extra_note_frames'] == 0


def longest_run(flags):
    best, run = 0, 0
    for value in flags:
        run = run+1 if value else 0
        best = max(best, run)
    return best


def paired_source_results(plan, baseline, adapted):
    """No pooled gain can hide a lost source occurrence or shorter correct hold."""
    if baseline.shape != adapted.shape or baseline.shape != (len(plan), 172, 88):
        raise ValueError('Paired tape shape mismatch')
    b, a = baseline >= SETTINGS['cutoff'], adapted >= SETTINGS['cutoff']
    rows, totals = [], defaultdict(Counter)
    for i, row in enumerate(plan):
        for component in row['components']:
            mask = component_frames(component)
            col = component['note']-SETTINGS['first_note']
            before, after = b[i, :, col] & mask, a[i, :, col] & mask
            delta = dict(example=i, source_key=component['source_key'], note=component['note'],
                expected_frames=int(mask.sum()), baseline_present=int(before.sum()),
                adapted_present=int(after.sum()), baseline_longest=longest_run(before),
                adapted_longest=longest_run(after))
            delta['present_delta'] = delta['adapted_present']-delta['baseline_present']
            delta['longest_delta'] = delta['adapted_longest']-delta['baseline_longest']
            rows.append(delta)
            aggregate = totals[component['source_key']]
            aggregate.update({k: delta[k] for k in ('expected_frames','baseline_present','adapted_present',
                                                    'baseline_longest','adapted_longest')})
            aggregate.update(occurrences=1, presence_losses=int(delta['present_delta'] < 0),
                             hold_losses=int(delta['longest_delta'] < 0))
    return dict(occurrence_count=len(rows), occurrences_losing_presence=sum(r['present_delta'] < 0 for r in rows),
        occurrences_losing_longest=sum(r['longest_delta'] < 0 for r in rows),
        no_occurrence_loss=all(r['present_delta'] >= 0 and r['longest_delta'] >= 0 for r in rows),
        by_source={key: dict(value) for key, value in sorted(totals.items())}, occurrence_deltas=rows,
        caveat='A same-pitch mixture counts presence once; these labels do not measure unison multiplicity.')
