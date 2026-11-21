"""Frozen direct-spectrum presence feasibility; pure/synthetic helpers.

Recorded inputs and fitting belong to the GitHub-only portable runner. No MIDI
policy, string assignment, future context or model selection is implemented here.
"""
from collections import Counter, defaultdict
import math

import numpy as np

from tools.pitch_detector_comparison import union_spans


SETTINGS = dict(sample_rate=96000, block=512, windows=[4096, 16384],
    grid_midi_low=28, grid_midi_high=120, bins_per_semitone=3,
    note_low=32, note_high=84, cutoff=0.5, input_trim_db=-9,
    train_examples=16384, calibration_examples=4096, test_examples=4096,
    train_seed=20261121, calibration_seed=20261122, test_seed=20261123,
    component_gains_db=[0, -6, -12, -18, -24], mixture_gains_db=[-12, -6, 0, 6],
    component_rms=0.05, normalization_floor=1e-12, silence_every=20,
    max_components=5)
MODEL_PARAMS = dict(hidden_layer_sizes=(128, 64), activation='relu', solver='adam',
    alpha=0.0001, batch_size=128, learning_rate_init=0.001, max_iter=80,
    shuffle=True, random_state=20261121, early_stopping=False, tol=0.0,
    n_iter_no_change=81)
ROLES = {1: 'train', 2: 'calibration', 3: 'test'}


def validate_manifest(manifest):
    """Validate every source interval before role assignment or audio access."""
    by_source = defaultdict(list)
    takes, keys, counts = [], set(), Counter()
    for source in manifest['files']:
        if source['sample_rate'] != SETTINGS['sample_rate']:
            raise ValueError('Source sample rate differs')
        for take in source['takes']:
            key = source['stem'] + ':' + str(take['label_index'])
            role = ROLES[take['calibration_pass']]
            left, right = take['start_sample'], take['end_sample']
            original_left, original_right = take['source_start_sample'], take['source_end_sample']
            if (key in keys or not 0 <= left < right <= source['sample_count']
                    or right-left < max(SETTINGS['windows'])
                    or not 0 <= original_left < original_right
                    or original_right-original_left != right-left
                    or not SETTINGS['note_low'] <= take['midi_note'] <= SETTINGS['note_high']
                    or take['string_mask'] <= 0
                    or take['string_mask'] & (take['string_mask']-1)):
                raise ValueError('Invalid source take: '+key)
            keys.add(key)
            counts[role] += 1
            item = dict(take, key=key, stem=source['stem'], role=role)
            takes.append(item)
            by_source[source['original_wave_sha256']].append((original_left, original_right, role, key))
    for intervals in by_source.values():
        ordered = sorted(intervals)
        for i, (left, right, role, key) in enumerate(ordered):
            for next_left, next_right, next_role, next_key in ordered[i+1:]:
                if next_left >= right:
                    break
                if role != next_role:
                    raise ValueError('Original audio crosses source roles: '+key+' / '+next_key)
    return takes, dict(counts)


def mixture_plan(takes, *, role, count, seed):
    """All components come from one source role; anchor every retained take."""
    sources = [row for row in takes if row['role'] == role]
    groups = defaultdict(list)
    for row in sources:
        groups[row['string_mask']].append(row)
    if not sources or len(groups) < SETTINGS['max_components']:
        raise ValueError('Insufficient source strings')
    if count-count//SETTINGS['silence_every']-1 < len(sources):
        raise ValueError('Insufficient examples to retain every source')
    rng = np.random.default_rng(seed)
    result, anchored = [], 0
    for i in range(count):
        if i % SETTINGS['silence_every'] == 0:
            result.append(dict(example=i, role=role, gain_db=0, components=[]))
            continue
        anchor = sources[anchored] if anchored < len(sources) else sources[int(rng.integers(len(sources)))]
        anchored += 1
        n = int(rng.integers(1, SETTINGS['max_components']+1))
        others = sorted(set(groups)-{anchor['string_mask']})
        strings = rng.choice(others, n-1, replace=False).tolist()
        chosen = [anchor] + [groups[s][int(rng.integers(len(groups[s])))] for s in strings]
        components = []
        for take in chosen:
            left = int(rng.integers(take['start_sample'], take['end_sample']-max(SETTINGS['windows'])+1))
            components.append(dict(source_key=take['key'], stem=take['stem'],
                string_mask=take['string_mask'], note=take['midi_note'], crop_begin=left,
                crop_end=left+max(SETTINGS['windows']),
                gain_db=int(rng.choice(SETTINGS['component_gains_db']))))
        result.append(dict(example=i, role=role, gain_db=int(rng.choice(SETTINGS['mixture_gains_db'])),
                           components=components))
    return result


class SpectrumFeatures:
    def __init__(self):
        midi = np.arange(SETTINGS['grid_midi_low']*SETTINGS['bins_per_semitone'],
                         SETTINGS['grid_midi_high']*SETTINGS['bins_per_semitone']+1)/SETTINGS['bins_per_semitone']
        self.frequency = 440.0 * 2.0**((midi-69.0)/12.0)
        self.windows = {n: np.hanning(n) for n in SETTINGS['windows']}
        self.fft_frequency = {n: np.fft.rfftfreq(n, 1/SETTINGS['sample_rate']) for n in self.windows}
        self.names = [name for n in SETTINGS['windows'] for name in
            [*(f'w{n}:midi{m:.6f}:relative_db' for m in midi), f'w{n}:rms_db']]

    def __call__(self, past):
        past = np.asarray(past, dtype=np.float64)
        if past.shape != (max(SETTINGS['windows']),) or not np.isfinite(past).all():
            raise ValueError('Expected one finite trailing context')
        out = []
        for n, window in self.windows.items():
            signal = past[-n:]
            rms2 = float(np.mean(signal*signal))
            spectrum = np.fft.rfft(signal*window)/window.sum()
            power = np.interp(self.frequency, self.fft_frequency[n], np.abs(spectrum)**2)
            relative = 10*np.log10(np.maximum(power, 1e-20)/max(rms2, 1e-12))
            absolute = np.clip(10*math.log10(max(rms2, 1e-12)), -120, 20)
            out.extend((np.clip(relative, -100, 20), np.array([absolute])))
        return np.concatenate(out)


def trailing_context(wave, end):
    """The caller may supply a whole recording, but future samples are never read."""
    if not 0 <= end <= len(wave):
        raise ValueError('Invalid source end')
    n = max(SETTINGS['windows'])
    result = np.zeros(n, dtype=np.float64)
    begin = max(0, end-n)
    if begin < end:
        result[-(end-begin):] = wave[begin:end]
    return result


def render_mixture(row, waves):
    n = max(SETTINGS['windows'])
    result = np.zeros(n, dtype=np.float64)
    target = np.zeros(SETTINGS['note_high']-SETTINGS['note_low']+1, dtype=bool)
    for component in row['components']:
        clip = waves[component['stem']][component['crop_begin']:component['crop_end']]
        if clip.shape != (n,) or not np.isfinite(clip).all():
            raise ValueError('Invalid mixture crop')
        rms = float(np.sqrt(np.mean(np.square(clip, dtype=np.float64))))
        gain = SETTINGS['component_rms']/max(rms, SETTINGS['normalization_floor'])
        result += clip * gain * 10**(component['gain_db']/20)
        target[component['note']-SETTINGS['note_low']] = True
    result *= 10**(row['gain_db']/20)
    return result, target


def classification_summary(probability, targets):
    probability, targets = np.asarray(probability), np.asarray(targets, dtype=bool)
    if probability.shape != targets.shape or not np.isfinite(probability).all():
        raise ValueError('Invalid predictions')
    predicted = probability >= SETTINGS['cutoff']
    def metrics(mask):
        truth, guess = targets[mask], predicted[mask]
        tp = int((truth & guess).sum())
        fp = int((~truth & guess).sum())
        fn = int((truth & ~guess).sum())
        return dict(examples=len(truth), true_positive=tp, false_positive=fp, false_negative=fn,
            precision_percent=100*tp/(tp+fp) if tp+fp else 0.0,
            recall_percent=100*tp/(tp+fn) if tp+fn else None,
            exact_set_percent=100*float(np.all(truth == guess, axis=1).mean()) if len(truth) else None)
    per_note = []
    for col in range(targets.shape[1]):
        truth, guess = targets[:, col], predicted[:, col]
        per_note.append(dict(note=col+SETTINGS['note_low'], support=int(truth.sum()),
            true_positive=int((truth & guess).sum()), false_positive=int((~truth & guess).sum()),
            false_negative=int((truth & ~guess).sum())))
    return dict(overall=metrics(np.ones(len(targets), dtype=bool)),
        by_distinct_pitch_count={str(n): metrics(targets.sum(axis=1) == n)
                                for n in sorted(set(targets.sum(axis=1).tolist()))},
        per_note=per_note, silence_false_predictions=int(predicted[~targets.any(axis=1)].sum()))


def representation_gate(summary):
    row = summary['overall']
    return (row['precision_percent'] >= 95 and row['recall_percent'] is not None
            and row['recall_percent'] >= 80 and row['exact_set_percent'] >= 70)


def fifo_clock(source_ends, service_ns):
    if len(source_ends) != len(service_ns):
        raise ValueError('Timing length mismatch')
    last_end, finish = 0, 0
    rows = []
    for end, service in zip(source_ends, service_ns):
        end, service = int(end), int(service)
        if end <= last_end or service < 0:
            raise ValueError('Nonmonotonic source or negative service time')
        arrival = (end*1_000_000_000+SETTINGS['sample_rate']-1)//SETTINGS['sample_rate']
        start = max(arrival, finish)
        finish = start+service
        rows.append((end, arrival, service, finish, start-arrival))
        last_end = end
    return np.asarray(rows, dtype=np.int64).reshape(-1, 5)


def prediction_spans(probability, starts, sample_count):
    """Raw threshold occupancy; EOF closure is a scoring boundary, not a NoteOff."""
    probability, starts = np.asarray(probability), np.asarray(starts, dtype=np.int64)
    if (probability.shape != (len(starts), SETTINGS['note_high']-SETTINGS['note_low']+1)
            or not np.isfinite(probability).all() or np.any(np.diff(starts) < 0)
            or np.any(starts < 0)):
        raise ValueError('Invalid decision tape')
    clipped = np.minimum(starts, sample_count)
    ends = np.r_[clipped[1:], sample_count]
    spans = [(int(left), int(right), int(col+SETTINGS['note_low']))
        for row, left, right in zip(probability, clipped, ends) if right > left
        for col in np.flatnonzero(row >= SETTINGS['cutoff'])]
    return union_spans(spans, sample_count=sample_count)
