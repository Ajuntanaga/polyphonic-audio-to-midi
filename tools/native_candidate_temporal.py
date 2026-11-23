"""Causal native-candidate features; no recordings, fitting or I/O here."""
import math

import numpy as np

from tools.basic_pitch_temporal_reliability import MODEL_PARAMS
from tools.pitch_detector_comparison import union_spans


DIRECT_FIELDS = (
    'selection active score_ratio fund_ratio band_score band_fund direct local '
    'evidence cal_direct best_cal second_cal phase_valid phase_updates age attack '
    'release evidence_ticks evidence_gap fine_valid shadow_interval shadow_kind '
    'selector_pool_member selector_raw_score selector_best_adjusted_score '
    'selector_voice_count selector_open_count onset_observed'
).split()
MASK_FIELDS = ('playable_mask cal_mask fine_mask committed_mask selector_option_mask '
               'selector_positive_mask selector_used_mask').split()
BASE_NAMES = DIRECT_FIELDS + [name+'_count' for name in MASK_FIELDS] + [
    'cal_margin', 'onset', 'phase_abs_cents', 'log_score_energy',
    'log_fund_energy', 'log_input_power']
HISTORY_FIELDS = ('active score_ratio fund_ratio band_score band_fund onset '
                  'phase_abs_cents selector_best_adjusted_score '
                  'log_score_energy log_fund_energy').split()
LAGS = (1, 4, 16, 64)
FEATURE_NAMES = BASE_NAMES + [f'{name}_lag{lag}' for lag in LAGS for name in HISTORY_FIELDS]


def eligible(candidate, quiet):
    """Sufficient legacy inclusion predicate, independent of annotation expansion.

    Retaining only freshly observed ordinary decisions prevents stale diagnostic
    energy from quiet dispositions being treated as a new observation.
    """
    return (quiet == 0 and candidate['energy_observed'] == 1
            and candidate['score_ratio'] >= 0.20
            and bool(candidate['direct'])
            and bool(candidate['local'] or candidate['evidence']))


def base_features(candidate, input_power):
    c = candidate
    if not math.isfinite(input_power) or input_power < 0:
        raise ValueError('Input power must be finite and nonnegative')
    values = [c[name] for name in DIRECT_FIELDS]
    values += [int(c[name]).bit_count() for name in MASK_FIELDS]
    values += [c['best_cal']-c['second_cal'],
               c['onset'] if c['onset_observed'] else np.nan,
               abs(c['phase_cents']) if c['phase_valid'] else np.nan]
    values += [math.log10(max(value, 1e-30))
               for value in (c['score_energy'], c['fund_energy'], input_power)]
    result = np.asarray(values, dtype=np.float32)
    if np.isinf(result).any():
        raise ValueError('Feature overflow')
    return result


class CausalHistory:
    """A fixed decision-index ring. Excluded rows never enter any history."""
    def __init__(self):
        self.history = np.full((max(LAGS)+1, 128, len(BASE_NAMES)), np.nan, dtype=np.float32)
        self.indices = [BASE_NAMES.index(name) for name in HISTORY_FIELDS]
        self.last_tick = None

    def frame(self, tick, quiet, candidates, input_power):
        if self.last_tick is not None and tick != self.last_tick+1:
            raise ValueError('Decision ticks must be contiguous')
        self.last_tick = tick
        slot = tick % len(self.history)
        self.history[slot].fill(np.nan)
        # Annotation-added candidates are rejected before storage, including
        # before they could affect a later eligible row's history.
        kept = [(note, c) for note, c in sorted(candidates.items()) if eligible(c, quiet)]
        result = []
        for note, c in kept:
            self.history[slot, note] = base_features(c, input_power)
            parts = [self.history[slot, note]]
            for lag in LAGS:
                parts.append(self.history[(tick-lag) % len(self.history), note, self.indices])
            result.append((note, np.concatenate(parts)))
        return result


def full_interval_targets(starts, ends, notes, labels, sample_count):
    """Annotations are first used here, after feature creation, only as targets."""
    expected = union_spans([(int(r['start_sample']), int(r['end_sample']), int(r['midi_note']))
                            for r in labels], sample_count=sample_count)
    target = np.zeros(len(starts), dtype=bool)
    for left, right, note in expected:
        target |= (notes == note) & (starts >= left) & (ends <= right)
    return target


def addition_spans(probability, cutoff, starts, ends, notes, sample_count):
    return union_spans([(int(a), int(b), int(n)) for a, b, n, p in
                       zip(starts, ends, notes, probability) if p >= cutoff],
                      sample_count=sample_count)
