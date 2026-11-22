"""Matched-crop component/mixture attribution; synthetic or saved arrays only.

Targets remain the intended source labels. An extra pitch found in a solo is
an association, not attribution of the mixture's extra to that component.
"""
import math

import numpy as np

from tools.direct_spectrum_learning import SETTINGS, render_mixture


PROBABILITY_ATOL = 1e-6
RECOMPOSITION_ATOL = 1e-14
PRESENCE_KEYS = ('retained', 'emerged_after_sum', 'lost_after_sum', 'already_missing_alone')


def probabilities(value, rows):
    value = np.asarray(value)
    if (value.shape != (rows, 53) or not np.isfinite(value).all()
            or (value < 0).any() or (value > 1).any()):
        raise ValueError('Invalid probability matrix')
    return value


def require_reproduction(actual, expected, cutoff):
    expected = probabilities(expected, len(expected))
    actual = probabilities(actual, len(expected))
    if not math.isfinite(cutoff) or not 0 < cutoff <= 1:
        raise ValueError('Invalid frozen cutoff')
    max_error = float(np.max(np.abs(actual - expected), initial=0))
    changed = int(np.count_nonzero((actual >= cutoff) != (expected >= cutoff)))
    if max_error > PROBABILITY_ATOL or changed:
        raise ValueError(f'Frozen output reproduction failed: error={max_error}, changed={changed}')
    return dict(max_absolute_probability_error=max_error, changed_decisions=changed)


def paired_audio(row, waves):
    """Use the original renderer for the mixture AND every component alone.

    The solo keeps the component's crop, normalization, gain and global gain.
    It is never renormalized to the complete mixture's level.
    """
    mixed, targets = render_mixture(row, waves)
    solos = [render_mixture(dict(row, components=[component]), waves)[0]
             for component in row['components']]
    recomposed = np.zeros_like(mixed)
    for solo in solos:
        recomposed += solo
    error = float(np.max(np.abs(recomposed - mixed), initial=0))
    if error > RECOMPOSITION_ATOL:
        raise ValueError(f'Component recomposition error: {error}')
    return mixed, targets, solos, error


def pitch_band(note):
    return 'below48' if note < 48 else '48-59' if note < 60 else '60-71' if note < 72 else '72+'


def relative_level(level, maximum):
    if level == 0 or maximum == 0:
        return 'silent_component'
    db = round(20 * math.log10(level / maximum), 6)
    return '0_to_-6dB' if db >= -6 else '-6_to_-12dB' if db >= -12 else '-12_to_-18dB' if db >= -18 else 'below_-18dB'


def add(bucket, values):
    for key, value in values.items():
        bucket[key] = bucket.get(key, 0) + int(value)


class PairedCensus:
    def __init__(self, cutoff):
        if not math.isfinite(cutoff) or not 0 < cutoff <= 1:
            raise ValueError('Invalid frozen cutoff')
        self.cutoff = cutoff
        self.report = dict(overall={}, by_component_count={}, by_distinct_pitch_count={},
                           by_pitch_band={}, by_relative_component_level={})

    def add(self, row, mixture_probability, solo_probability, solo_rms):
        components = row['components']
        mixture = probabilities(np.asarray(mixture_probability)[None, :], 1)[0] >= self.cutoff
        solo = probabilities(solo_probability, len(components)) >= self.cutoff
        levels = np.asarray(solo_rms, dtype=np.float64)
        if levels.shape != (len(components),) or not np.isfinite(levels).all() or (levels < 0).any():
            raise ValueError('Invalid component RMS')
        notes = [int(c['note']) for c in components]
        if any(n < 32 or n > 84 for n in notes):
            raise ValueError('Expected note outside model range')
        expected = set(notes)
        counts = dict(examples=1, components=len(components), expected=len(expected),
                      mixture_present=0, mixture_missing=0, extra_in_any_solo=0,
                      extra_new_after_sum=0, **{key: 0 for key in PRESENCE_KEYS})
        own_found = []
        maximum = float(np.max(levels, initial=0))
        for note in sorted(expected):
            index = note - 32
            owners = [i for i, value in enumerate(notes) if value == note]
            alone = bool(solo[owners, index].any())
            present = bool(mixture[index])
            key = ('retained' if alone else 'emerged_after_sum') if present else (
                'lost_after_sum' if alone else 'already_missing_alone')
            own_found.append(alone)
            counts[key] += 1
            counts['mixture_present' if present else 'mixture_missing'] += 1
            per_note = dict(expected=1, **{k: int(k == key) for k in PRESENCE_KEYS})
            add(self.report['by_pitch_band'].setdefault(pitch_band(note), {}), per_note)
            # A unison is one expected pitch; strongest own component defines
            # its level relative to the strongest component in this mixture.
            level_key = relative_level(float(levels[owners].max()), maximum)
            add(self.report['by_relative_component_level'].setdefault(level_key, {}), per_note)
        for index in np.flatnonzero(mixture):
            note = int(index) + 32
            if note in expected:
                continue
            key = 'extra_in_any_solo' if solo[:, index].any() else 'extra_new_after_sum'
            counts[key] += 1
            add(self.report['by_pitch_band'].setdefault(pitch_band(note), {}), {key: 1})
        counts['mixture_extras'] = counts['extra_in_any_solo'] + counts['extra_new_after_sum']
        exact = counts['mixture_missing'] == 0 and counts['mixture_extras'] == 0
        counts['complete_sets'] = int(exact)
        # Silence has no own-component test; do not count vacuous truth as one.
        all_found = bool(expected) and all(own_found)
        counts['all_own_pitches_found_alone'] = int(all_found)
        counts['complete_sets_when_all_own_found'] = int(all_found and exact)
        add(self.report['overall'], counts)
        add(self.report['by_component_count'].setdefault(str(len(components)), {}), counts)
        add(self.report['by_distinct_pitch_count'].setdefault(str(len(expected)), {}), counts)
        return counts

    def finish(self):
        counts = self.report['overall']
        if counts['expected'] != sum(counts[k] for k in PRESENCE_KEYS):
            raise ValueError('Presence census does not reconcile')
        if counts['mixture_missing'] != counts['lost_after_sum'] + counts['already_missing_alone']:
            raise ValueError('Missing census does not reconcile')
        return self.report
