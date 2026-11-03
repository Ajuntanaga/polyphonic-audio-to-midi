"""Paired descriptor measurements from controlled, same-waveform mixtures.

This measures the effect of adding a recorded note to one fixed recording.
It does not estimate independent-performance uncertainty or MIDI improvement.
Missing or reserved observations stay unavailable, never a zero margin.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import itertools
import math
from pathlib import Path
import struct

from tools.string_likelihood_decomposition import pair_margins


def read_float_wave(path):
    """Read the existing mono float32 corpus without decoding/resampling it."""
    import numpy as np
    raw = Path(path).read_bytes()
    if raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
        raise ValueError('expected RIFF WAVE')
    if len(raw) < 12 or struct.unpack_from('<I', raw, 4)[0] + 8 != len(raw):
        raise ValueError('incomplete RIFF WAVE')
    fmt = payload = None
    cursor = 12
    while cursor + 8 <= len(raw):
        kind, length = struct.unpack_from('<4sI', raw, cursor)
        cursor += 8
        if cursor + length > len(raw):
            raise ValueError('incomplete WAVE chunk')
        chunk = raw[cursor:cursor + length]
        if kind == b'fmt ':
            fmt = struct.unpack('<HHIIHH', chunk[:16])
        elif kind == b'data':
            payload = chunk
        cursor += length + (length & 1)
    if (fmt is None or fmt[0:2] != (3, 1) or fmt[4:] != (4, 32) or
            fmt[2] <= 0 or fmt[3] != fmt[2] * 4 or payload is None or len(payload) % 4):
        raise ValueError('expected mono float32 WAVE with a valid clock')
    values = np.frombuffer(payload, dtype='<f4').copy()
    if not np.isfinite(values).all():
        raise ValueError('nonfinite waveform')
    return fmt[2], values


def write_float_wave(path, sample_rate, values):
    import numpy as np
    values = np.asarray(values, dtype='<f4')
    if values.ndim != 1 or not np.isfinite(values).all() or sample_rate <= 0:
        raise ValueError('invalid output waveform')
    payload = values.tobytes()
    fmt = struct.pack('<HHIIHH', 3, 1, sample_rate, sample_rate * 4, 4, 32)
    body = b'WAVEfmt ' + struct.pack('<I', len(fmt)) + fmt
    body += b'data' + struct.pack('<I', len(payload)) + payload
    Path(path).write_bytes(b'RIFF' + struct.pack('<I', len(body)) + body)


def controlled_mixtures(target, interferers, *, prefix, suffix, levels=(-12.0, 0.0)):
    """Keep one target gain/onset across solo and every declared RMS mixture.

    Float32 output rounding is measured explicitly. Any attenuation needed to
    prevent clipping is shared by all cases, never normalized per mixture.
    """
    import numpy as np
    target = np.asarray(target, dtype=np.float64)
    if (target.ndim != 1 or not len(target) or not np.isfinite(target).all() or
            prefix < 0 or suffix < 0 or not levels or
            not all(math.isfinite(level) for level in levels)):
        raise ValueError('invalid target, padding or levels')
    target_rms = float(np.sqrt(np.mean(target ** 2)))
    if target_rms <= 0:
        raise ValueError('silent target')
    raw_cases = [('solo', target, dict(interferer=None, relative_rms_db=None,
                                     interferer_scale=0.0))]
    for name, waveform in interferers.items():
        wave = np.asarray(waveform, dtype=np.float64)
        if wave.shape != target.shape or not np.isfinite(wave).all():
            raise ValueError('interferer geometry differs or is nonfinite')
        rms = float(np.sqrt(np.mean(wave ** 2)))
        if rms <= 0:
            raise ValueError('silent interferer')
        for level in levels:
            scale = target_rms * 10 ** (level / 20) / rms
            raw_cases.append((f'{name}_{level:g}dB', target + scale * wave,
                              dict(interferer=name, relative_rms_db=level,
                                   interferer_scale=scale)))
    peak = max(float(np.max(np.abs(wave))) for _, wave, _ in raw_cases)
    gain = min(1.0, 0.95 / peak)
    target_bytes = np.asarray(target * gain, dtype='<f4').tobytes()
    common = dict(target_samples=len(target), prefix_samples=prefix, suffix_samples=suffix,
                  common_gain=gain, target_rms_before_gain=target_rms,
                  target_component_sha256=hashlib.sha256(target_bytes).hexdigest())
    cases = {}
    for name, wave, metadata in raw_cases:
        exact = wave * gain
        rounded = np.asarray(exact, dtype='<f4')
        error = rounded.astype(np.float64) - exact
        cases[name] = dict(audio=np.pad(rounded, (prefix, suffix)),
                           metadata={**metadata, **common,
                                     'peak': float(np.max(np.abs(rounded))),
                                     'rounding_max_abs': float(np.max(np.abs(error)))})
    return cases


def age_group(sample, start, sample_rate):
    age = (sample - start) / sample_rate
    return 'attack_0_100ms' if age < 0.1 else 'early_100_350ms' if age < 0.35 else 'sustain_350ms_plus'


def observations(rows, *, note, lane, competitor, start, end, sample_rate,
                 sample_count, stride):
    """Collect one target/string pair at the same native sampled decisions."""
    if not (0 <= lane < 8 and 0 <= competitor < 8 and lane != competitor and
            0 <= start < end <= sample_count and stride > 0 and sample_rate > 0):
        raise ValueError('invalid controlled observation geometry')
    available, coverage = {}, Counter()
    expected_grid = set(range(stride - 1, sample_count, stride))
    target_grid = {sample for sample in expected_grid if start <= sample < end}
    previous, row_count = -1, 0
    seen_targets = set()
    for sample, group in itertools.groupby(rows, lambda row: int(row['sample'])):
        frame = list(group)
        if (sample <= previous or sample not in expected_grid or
                any(int(row['tick']) * 64 - 1 != sample for row in frame)):
            raise ValueError('invalid sampled decision clock')
        previous = sample
        row_count += len(frame)
        if len({int(row['note']) for row in frame}) != len(frame):
            raise ValueError('duplicate note at sampled decision')
        if sample not in target_grid:
            continue
        matching = [row for row in frame if int(row['note']) == note]
        if not matching:
            continue
        seen_targets.add(sample)
        row = matching[0]
        if not int(row['observed']) or int(row['fixed_context']):
            coverage['not_current_observation'] += 1
            continue
        if not (int(row['complete_calibration']) and int(row['posterior_observation_available'])):
            coverage['likelihood_unavailable'] += 1
            continue
        pair = (1 << lane) | (1 << competitor)
        reserved = int(row['reserved_coasting']) | int(row['reserved_extras'])
        if pair & reserved or pair & ~int(row['playable']):
            coverage['reserved_or_infeasible_pair'] += 1
            continue
        available[sample] = dict(age=age_group(sample, start, sample_rate),
                                 margins=pair_margins(row, lane, competitor))
        coverage['available'] += 1
    coverage['target_grid_frames'] = len(target_grid)
    coverage['missing_target_row'] = len(target_grid - seen_targets)
    return dict(coverage=dict(coverage), trace_rows=row_count, observations=available,
                geometry=dict(note=note, lane=lane, competitor=competitor, start=start,
                              end=end, sample_rate=sample_rate, sample_count=sample_count,
                              stride=stride))


def compare_to_solo(solo, mixed):
    """Pair identical clock positions; report both availability and sign flips."""
    if solo['geometry'] != mixed['geometry']:
        raise ValueError('target geometry differs between cases')
    left, right = solo['observations'], mixed['observations']
    common = sorted(set(left) & set(right))
    groups = {}
    for sample in common:
        before, after = left[sample], right[sample]
        if before['age'] != after['age']:
            raise ValueError('target onset/age differs between cases')
        group = groups.setdefault(before['age'], [])
        group.append((before['margins'], after['margins']))
    result = dict(common_frames=len(common),
                  solo_available_only=len(set(left) - set(right)),
                  mixed_available_only=len(set(right) - set(left)), by_age={})
    for age, pairs in groups.items():
        n = len(pairs)
        terms = {}
        for term in ('descriptor', 'profile', 'cents', 'detuning', 'total'):
            a, b = [p[0][term] for p in pairs], [p[1][term] for p in pairs]
            if not all(math.isfinite(value) for value in a + b):
                raise ValueError('nonfinite paired margin')
            an, bn = sum(v < -1e-9 for v in a), sum(v < -1e-9 for v in b)
            terms[term] = dict(solo_mean=sum(a) / n, mixed_mean=sum(b) / n,
                               mean_change=sum(y - x for x, y in zip(a, b)) / n,
                               solo_negative_frames=an, mixed_negative_frames=bn,
                               solo_negative_percent=100 * an / n,
                               mixed_negative_percent=100 * bn / n,
                               negative_change_percentage_points=100 * (bn - an) / n,
                               positive_to_negative=sum(x > 1e-9 and y < -1e-9 for x, y in zip(a, b)),
                               negative_to_positive=sum(x < -1e-9 and y > 1e-9 for x, y in zip(a, b)))
        result['by_age'][age] = dict(paired_frames=n, terms=terms)
    return result
