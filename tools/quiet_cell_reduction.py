"""Stream saved resonator observations into fixed, causal interval projections.

No audio, policy, label scoring, or pitch classification. Missing anchors stay
missing; raw state is retained beside the memory-subtracted measurement.
"""
from collections import Counter, deque
from dataclasses import dataclass
import math


CELL_HEADER = ('sample tick quiet note available input_power decay').split() + [
    f'h{h}_{field}' for h in range(1, 7) for field in ('hz', 'real', 'imag')]
EXTRA_HEADER = ('window_ids anchor_sample interval_samples interval_status '
                'interval_power_delta interval_power').split() + [
    f'h{h}_interval_{field}' for h in range(1, 7) for field in ('real', 'imag')]
OUTPUT_HEADER = CELL_HEADER + EXTRA_HEADER


@dataclass(frozen=True)
class Cell:
    sample: int
    tick: int
    quiet: int
    note: int
    available: bool
    power: float
    decay: float
    harmonics: tuple

    @classmethod
    def parse(cls, fields):
        if len(fields) != len(CELL_HEADER):
            raise ValueError('Wrong raw-cell column count')
        sample, tick, quiet, note, available = map(int, fields[:5])
        values = list(map(float, fields[5:]))
        if (sample < 0 or tick < 0 or quiet < 0 or not 0 <= note < 128
                or available not in (0, 1) or not all(map(math.isfinite, values))):
            raise ValueError('Invalid raw-cell values')
        power, decay = values[:2]
        harmonics = tuple(tuple(values[i:i+3]) for i in range(2, len(values), 3))
        if power < 0 or any(hz < 0 for hz, _, _ in harmonics):
            raise ValueError('Negative power or frequency')
        if available:
            if not 0 < decay < 1:
                raise ValueError('Invalid available-cell decay')
            if any(hz == 0 and (real != 0 or imag != 0) for hz, real, imag in harmonics):
                raise ValueError('Disabled harmonic carries a measurement')
        elif any(values):
            raise ValueError('Unavailable row carries a measurement')
        return cls(sample, tick, quiet, note, bool(available), power, decay, harmonics)


def interval_projection(current, anchor, samples):
    """Subtract a**N old baseband state, with no carrier rotation or fit."""
    empty = dict(status='missing_anchor', power_delta=None, power=None, harmonics=None)
    if not current.available:
        return dict(empty, status='unavailable_current')
    if anchor is None:
        return empty
    if current.sample-anchor.sample != samples or current.note != anchor.note:
        raise ValueError('Anchor is not the exact same-pitch sample lag')
    if not anchor.available:
        return dict(empty, status='unavailable_anchor')
    if (current.decay != anchor.decay or
            [h[0] for h in current.harmonics] != [h[0] for h in anchor.harmonics]):
        return dict(empty, status='configuration_changed')
    exponent = samples * math.log(current.decay)
    attenuation = math.exp(exponent)
    weight = -math.expm1(exponent)
    power_delta = current.power - attenuation * anchor.power
    harmonics = tuple(((now[1]-attenuation*old[1])/weight,
                       (now[2]-attenuation*old[2])/weight)
                      for now, old in zip(current.harmonics, anchor.harmonics))
    # Preserve a negative cancellation residual, never turn it into measured
    # zero power. The signed delta and a separate status allow later diagnosis.
    return dict(status='negative_power' if power_delta < 0 else 'ok',
                power_delta=power_delta,
                power=power_delta/weight if power_delta >= 0 else None,
                harmonics=harmonics)


def context_windows(marked, horizon, before_samples, after_samples):
    previous_end = -1
    windows = []
    for index, pair in enumerate(marked):
        if (len(pair) != 2 or any(type(n) is not int for n in pair)
                or not 0 <= pair[0] < pair[1] <= horizon or pair[0] < previous_end):
            raise ValueError('Invalid or overlapping marked intervals')
        start, end = pair
        previous_end = end
        windows.append(dict(id=index, marked_start=start, marked_end=end,
                            begin=max(0, start-before_samples),
                            end=min(horizon, end+after_samples)))
    return windows


def number(value):
    return '' if value is None else format(value, '.17g')


def reduce_stream(lines, output, *, marked, horizon, lag_samples,
                  before_samples, after_samples):
    """Retain every serialized pitch in the union of fixed boundary windows.

    Every input row is parsed, but only one lag of history per pitch is held.
    Window membership is descriptive and may include several window IDs. An
    overlapping row is written once. No label-dependent selection is made.
    """
    if (any(type(n) is not int for n in
            (horizon, lag_samples, before_samples, after_samples))
            or horizon <= 0 or lag_samples <= 0 or min(before_samples, after_samples) < 0):
        raise ValueError('Invalid interval specification')
    windows = context_windows(marked, horizon, before_samples, after_samples)
    if next(lines, '').strip() != '# m3_outcome_cells_v1' or \
            next(lines, '').rstrip('\r\n').split('\t') != CELL_HEADER:
        raise ValueError('Unexpected raw-cell header')
    output.write('# m3_quiet_cell_intervals_v1\n'+'\t'.join(OUTPUT_HEADER)+'\n')
    history = {}
    pending = deque()
    cursor = 0
    previous_key = (-1, -1)
    previous_tick = None
    frame_power = None
    rows = retained = 0
    statuses, quiet_statuses = Counter(), Counter()
    window_rows = Counter()
    max_history = 0
    for line in lines:
        fields = line.rstrip('\r\n').split('\t')
        current = Cell.parse(fields)
        key = (current.sample, current.note)
        if key <= previous_key:
            raise ValueError('Cell rows not strictly ordered by sample and pitch')
        if current.sample != previous_key[0]:
            previous_tick = current.tick
            frame_power = None
        elif current.tick != previous_tick:
            raise ValueError('Same sample has different decision ticks')
        if current.available:
            if frame_power is not None and current.power != frame_power:
                raise ValueError('Same sample has different measured input powers')
            frame_power = current.power
        previous_key = key
        rows += 1
        target = current.sample-lag_samples
        while pending and pending[0][0] < target:
            history.pop(pending.popleft())
        anchor = history.get((target, current.note))
        while cursor < len(windows) and windows[cursor]['end'] <= current.sample:
            cursor += 1
        ids = []
        index = cursor
        while index < len(windows) and windows[index]['begin'] <= current.sample:
            if current.sample < windows[index]['end']:
                ids.append(windows[index]['id'])
            index += 1
        if ids:
            projection = interval_projection(current, anchor, lag_samples)
            status = projection['status']
            statuses[status] += 1
            quiet_statuses[f'{current.quiet}:{status}'] += 1
            window_rows.update(ids)
            retained += 1
            harmonics = projection['harmonics']
            extra = [','.join(map(str, ids)), str(target), str(lag_samples), status,
                     number(projection['power_delta']), number(projection['power'])]
            extra.extend(number(value) for pair in (harmonics or [(None, None)]*6)
                         for value in pair)
            output.write('\t'.join(fields+extra)+'\n')
        history[key] = current
        pending.append(key)
        max_history = max(max_history, len(history))
    return dict(input_rows=rows, retained_rows=retained, interval_samples=lag_samples,
                status_counts=dict(statuses), quiet_status_counts=dict(quiet_statuses),
                windows=[dict(row, retained_rows=window_rows[row['id']]) for row in windows],
                max_history_rows=max_history, row_selection_uses_labels=False,
                interpretation='Interval forcing of a cell is not proof of a new note or independent pitch')
