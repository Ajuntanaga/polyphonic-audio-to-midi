"""Pure summary helpers for an observation, not an attack decision rule."""
from __future__ import annotations

import math


def mean(values):
    values = list(values)
    if not values:
        raise ValueError('Empty observation window')
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('Expected finite nonnegative powers')
    return sum(values) / len(values)


def rise_summary(times, powers, cue_ms, before_ms=60, after_ms=20, half_ms=20):
    """Maximum adjacent-window power rise inside the frozen cue neighborhood."""
    if len(times) != len(powers) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('Mismatched or unordered curve')
    # Ratios use the same epsilon, and retain levels so quiet ratios are visible.
    floor = 1e-24
    choices = []
    for center in times:
        if not cue_ms - before_ms <= center <= cue_ms + after_ms:
            continue
        if center - half_ms < times[0] or center + half_ms > times[-1]:
            continue
        pre = mean(p for t, p in zip(times, powers) if center - half_ms <= t < center)
        post = mean(p for t, p in zip(times, powers) if center <= t < center + half_ms)
        choices.append({'center_ms': center, 'power_ratio': (post + floor) / (pre + floor),
                        'rise_db': 10 * math.log10((post + floor) / (pre + floor)),
                        'before_dbfs': 10 * math.log10(pre + floor),
                        'after_dbfs': 10 * math.log10(post + floor)})
    if not choices:
        raise ValueError('No complete comparison in cue neighborhood')
    return max(choices, key=lambda row: row['power_ratio'])


def observation_summary(rows, cues):
    if not rows:
        raise ValueError('Empty curves')
    names = tuple(rows[0]['powers'])
    if any(tuple(row['powers']) != names for row in rows):
        raise ValueError('Power columns changed')
    return {name: {column: rise_summary([r['relative_ms'] for r in rows],
                                       [r['powers'][column] for r in rows], value)
                   for column in names} for name, value in cues.items()}
