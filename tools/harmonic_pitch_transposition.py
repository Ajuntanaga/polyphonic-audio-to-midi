"""Training-only coherent pitch shifts; recorded rendering belongs on GitHub."""
from collections import Counter
from copy import deepcopy
from fractions import Fraction
from functools import lru_cache
import gzip
import hashlib
import json
import math

import numpy as np

from tools.direct_spectrum_learning import SETTINGS, render_mixture
from tools.harmonic_source_variation import encoded_plan


TRANSPOSITION = dict(name='coherent_training_transposition_v1', seed=20261125,
    semitone_radius=6, denominator_limit=4096, maximum_pitch_error_cents=0.01,
    input_guard_samples=64, filter_half_length_factor=10, kaiser_beta=5.0,
    shift_rule='uniform legal nonzero integer shift per mixture; identity for silence or no legal shift',
    crop_rule='map original within-take crop quantile to guarded input support; no padding or wrapping',
    fitting='all clean training mixtures plus one companion each; unchanged 80 epochs, twice the optimizer steps',
    normalization='existing component RMS and gain after resampling',
    cutoff_and_training_gates='original unaugmented training plan',
    held_out='unchanged, never augmented')


@lru_cache(maxsize=13)
def resampling_ratio(shift):
    if not isinstance(shift, int) or abs(shift) > TRANSPOSITION['semitone_radius']:
        raise ValueError('Pitch shift exceeds frozen bounds')
    ratio = Fraction(2.0**(-shift/12)).limit_denominator(TRANSPOSITION['denominator_limit'])
    error = 1200*math.log2(ratio.denominator/ratio.numerator)-100*shift
    if abs(error) > TRANSPOSITION['maximum_pitch_error_cents']:
        raise ValueError('Rational pitch approximation exceeds tolerance')
    return ratio.numerator, ratio.denominator


def transpose_training_plan(plan, takes):
    """Metadata only: retain original identity/crop and pin shifted support/targets."""
    if not plan or any(row['role'] != 'train' for row in plan):
        raise ValueError('Pitch transposition is restricted to the training role')
    by_key = {take['key']: take for take in takes}
    result = deepcopy(plan)
    rng = np.random.default_rng(TRANSPOSITION['seed'])
    n = max(SETTINGS['windows'])
    guard = TRANSPOSITION['input_guard_samples']
    for row in result:
        if 'transpose_semitones' in row:
            raise ValueError('Training mixture was already transposed')
        notes = [c['note'] for c in row['components']]
        radius = TRANSPOSITION['semitone_radius']
        legal = [k for k in range(-radius, radius+1) if k and notes and
                 all(SETTINGS['note_low'] <= note+k <= SETTINGS['note_high'] for note in notes)]
        shift = int(rng.choice(legal)) if legal else 0
        up, down = resampling_ratio(shift)
        row.update(transpose_semitones=shift, resample_up=up, resample_down=down)
        output_begin = (guard*up+down-1)//down if shift else 0
        support_length = ((output_begin+n)*down+up-1)//up+guard if shift else n
        # Default SciPy FIR support expressed on the input clock is < 15 samples
        # for these ratios; 64 on both sides also covers alignment rounding.
        if shift and guard*up <= TRANSPOSITION['filter_half_length_factor']*max(up, down)+up:
            raise ValueError('Insufficient resampler guard')
        for c in row['components']:
            take = by_key[c['source_key']]
            left, right = take['start_sample'], take['end_sample']
            if (take['role'] != 'train' or take['stem'] != c['stem'] or
                    take['midi_note'] != c['note'] or take['string_mask'] != c['string_mask'] or
                    c['crop_end']-c['crop_begin'] != n or
                    not left <= c['crop_begin'] < c['crop_end'] <= right or
                    right-left < support_length):
                raise ValueError('Invalid training source provenance or support')
            available = right-left-support_length
            original_available = right-left-n
            begin = left+(c['crop_begin']-left)*available//max(1, original_available)
            c.update(source_note=c['note'], note=c['note']+shift,
                support_begin=begin, support_end=begin+support_length,
                output_begin=output_begin)
    return result


@lru_cache(maxsize=12)
def resampling_filter(up, down):
    from scipy.signal import firwin
    rate = max(up, down)
    return firwin(2*TRANSPOSITION['filter_half_length_factor']*rate+1,
                  1.0/rate, window=('kaiser', TRANSPOSITION['kaiser_beta']))


def transposed_component(wave, component, shift):
    """Resample a guarded in-label interval and discard both boundary regions."""
    up, down = resampling_ratio(shift)
    n = max(SETTINGS['windows'])
    begin, end = component['support_begin'], component['support_end']
    if not 0 <= begin < end <= len(wave):
        raise ValueError('Invalid transposition support')
    clip = np.asarray(wave[begin:end], dtype=np.float64)
    if not np.isfinite(clip).all():
        raise ValueError('Nonfinite transposition input')
    if shift:
        from scipy.signal import resample_poly
        guard = TRANSPOSITION['input_guard_samples']
        start = component['output_begin']
        if start*down < guard*up or (start+n)*down > (len(clip)-guard)*up:
            raise ValueError('Output crop touches resampler boundary')
        clip = resample_poly(clip, up, down, window=resampling_filter(up, down))[start:start+n]
    if clip.shape != (n,) or not np.isfinite(clip).all():
        raise ValueError('Invalid transposed output crop')
    return clip


def render_transposed_mixture(row, waves):
    # Reuse the original mixing/RMS/level semantics after the changed crop path.
    shifted = deepcopy(row)
    clips = {}
    for i, c in enumerate(shifted['components']):
        clips[str(i)] = transposed_component(waves[c['stem']], c, row['transpose_semitones'])
        c.update(stem=str(i), crop_begin=0, crop_end=max(SETTINGS['windows']))
    return render_mixture(shifted, clips)


def transposition_examples(plan_path, takes, waves, extractor, bulk):
    from tools.portable_basic_pitch_comparison import remote_only
    remote_only()  # Pure helpers above are exercised locally only on synthetic tones.
    plan = transpose_training_plan(json.loads(gzip.decompress(plan_path.read_bytes())), takes)
    encoded = encoded_plan(plan)
    path = bulk/'train-transposed-mixture-plan.json.gz'
    path.write_bytes(gzip.compress(encoded, mtime=0))
    x = np.empty((len(plan), len(extractor.names)), dtype=np.float64)
    y = np.empty((len(plan), SETTINGS['note_high']-SETTINGS['note_low']+1), dtype=bool)
    for i, row in enumerate(plan):
        audio, target = render_transposed_mixture(row, waves)
        x[i], y[i] = extractor(audio), target
    shifts = Counter(row['transpose_semitones'] for row in plan)
    return x, y, dict(parameters=TRANSPOSITION, plan_file=path.name,
        decoded_sha256=hashlib.sha256(encoded).hexdigest(), companion_mixtures=len(plan),
        shift_counts=dict(sorted(shifts.items())),
        identity_non_silence=sum(bool(r['components']) and r['transpose_semitones'] == 0 for r in plan),
        training_sources=len({c['source_key'] for row in plan for c in row['components']}),
        fitting='clean plus transposed companions', cutoff_and_gates='original clean training plan',
        held_out_augmented=False)
