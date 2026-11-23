"""Frozen descriptive restart evidence from saved, causal cell intervals.

No detector, audio, fitted rule, or event generation. Labels only classify
diagnostic units and deadlines. Missing measurements never become zero.
"""
from collections import Counter
import math
import random

from tools.quiet_cell_reduction import Cell, OUTPUT_HEADER


FEATURES = ('interval_fundamental_share', 'interval_harmonic_share',
            'recent_to_raw_harmonics', 'raw_fundamental_share')
HORIZONS = ('in_run', 'by_25ms')
STATUSES = {'ok', 'missing_anchor', 'unavailable_current', 'unavailable_anchor',
            'configuration_changed', 'negative_power'}


def ratio(numerator, denominator):
    if denominator <= 0:
        return None
    value = numerator / denominator
    if not math.isfinite(value) or value < 0:
        raise ValueError('Invalid derived feature')
    return value


def parse_row(fields):
    if len(fields) != len(OUTPUT_HEADER):
        raise ValueError('Wrong interval column count')
    cell = Cell.parse(fields[:25])
    row = dict(zip(OUTPUT_HEADER, fields))
    ids = list(map(int, row['window_ids'].split(',')))
    if ids != sorted(set(ids)) or not ids or ids[0] < 0:
        raise ValueError('Invalid window IDs')
    if int(row['interval_samples']) != 1920 or int(row['anchor_sample']) != cell.sample-1920:
        raise ValueError('Interval differs from frozen 20 ms')
    status = row['interval_status']
    if status not in STATUSES:
        raise ValueError('Unknown interval status')
    values = {}
    for key in OUTPUT_HEADER[29:]:
        if row[key] != '':
            values[key] = float(row[key])
            if not math.isfinite(values[key]):
                raise ValueError('Nonfinite interval measurement')
    features = dict.fromkeys(FEATURES)
    if cell.available:
        raw = [real*real+imag*imag for hz, real, imag in cell.harmonics if hz > 0]
        raw_sum = sum(raw)
        if cell.harmonics[0][0] > 0:
            features['raw_fundamental_share'] = ratio(
                cell.harmonics[0][1]**2+cell.harmonics[0][2]**2, cell.power)
        if status == 'ok':
            needed = OUTPUT_HEADER[29:]
            if set(values) != set(needed) or values['interval_power'] < 0 or values['interval_power_delta'] < 0:
                raise ValueError('Incomplete or negative ok interval')
            recent = [(values[f'h{i}_interval_real']**2+values[f'h{i}_interval_imag']**2)
                      for i in range(1, 7) if cell.harmonics[i-1][0] > 0]
            if cell.harmonics[0][0] > 0:
                fundamental = values['h1_interval_real']**2+values['h1_interval_imag']**2
                features['interval_fundamental_share'] = ratio(fundamental, values['interval_power'])
            features['interval_harmonic_share'] = ratio(sum(recent), values['interval_power'])
            features['recent_to_raw_harmonics'] = ratio(sum(recent), raw_sum)
    elif status != 'unavailable_current':
        raise ValueError('Unavailable current has inconsistent status')
    return cell, ids, status, features


def expected_ticks(begin, end):
    first = begin + ((63-begin) % 64)
    return max(0, (end-1-first)//64+1)


def accumulator(begin, end):
    return dict(begin=begin, end=end, expected_decisions=expected_ticks(begin, end),
                rows=0, quiet_counts={}, status_counts={},
                features={key: dict(count=0, maximum=None, maximum_sample=None)
                          for key in FEATURES})


def observe(acc, sample, quiet, status, features):
    if not acc['begin'] <= sample < acc['end']:
        return
    acc['rows'] += 1
    for key, value in (('quiet_counts', str(quiet)), ('status_counts', status)):
        acc[key][value] = acc[key].get(value, 0)+1
    for key, value in features.items():
        if value is None:
            continue
        dst = acc['features'][key]
        dst['count'] += 1
        if dst['maximum'] is None or value > dst['maximum']:
            dst['maximum'], dst['maximum_sample'] = value, sample


def make_units(census, mask):
    if census['rate'] != 96000 or mask['rate'] != 96000 or census['horizon'] != mask['horizon']:
        raise ValueError('Dataset clock differs')
    marked = mask['marked_intervals']
    if len(marked) != census['marked_runs']:
        raise ValueError('Marked run count differs')
    previous = -1
    for begin, end in marked:
        if not 0 <= begin < end <= mask['horizon'] or begin < previous:
            raise ValueError('Marked intervals invalid')
        previous = end
    labels = mask['comparison']['label_deltas']
    units = []
    original = Counter()
    for si, span in enumerate(census['truncated_spans']):
        original[span['cls']] += 1
        a, b = span['span']
        if a != span['start'] or not a <= span['cut'] < b:
            raise ValueError('Census span differs')
        matching_runs = [(i, start, end) for i, (start, end) in enumerate(marked) if a <= start < b]
        if not matching_runs or matching_runs[0][1:] != (span['cut'], span['run_end']):
            raise ValueError('Census first cut differs from marked intervals')
        for wi, start, end in matching_runs:
            deadline = min(end+2400, b, marked[wi+1][0] if wi+1 < len(marked) else mask['horizon'])
            same = [r for r in labels if r['midi_note'] == span['pitch']
                    and r['start_sample'] < min(deadline, b) and r['end_sample'] > max(start, a)]
            new = [r for r in same if start <= r['start_sample'] < deadline]
            cls = 'positive' if new else 'continuing' if same else 'negative'
            label_views = []
            for r in new:
                budget = min(2400, r['current_present_samples']//20,
                             r['current_longest_present_samples']//20)
                limit = min(deadline, r['start_sample']+budget+1)
                label_views.append(dict(label=r['label_index'], start=r['start_sample'],
                    budget_samples=budget, onset_vs_run_end=r['start_sample']-end,
                    measurements=accumulator(start, limit)))
            units.append(dict(id=len(units), original_span_id=si, original_span_class=span['cls'],
                note=span['pitch'], span=[a, b], run_id=wi, run=[start, end], classification=cls,
                labels=label_views, in_run=accumulator(start, min(end, b)),
                by_25ms=accumulator(start, deadline)))
    return units, dict(original)


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    position = (len(values)-1)*p
    low = int(position)
    return values[low] + (values[min(low+1, len(values)-1)]-values[low])*(position-low)


def auc_groups(rows):
    grouped = {}
    for score, cls, run in rows:
        pair = grouped.setdefault(score, (Counter(), Counter()))
        pair[0 if cls == 'positive' else 1][run] += 1
    return [grouped[score] for score in sorted(grouped)]


def weighted_auc(groups, weights):
    positives = negatives = favorable = 0.0
    for pos, neg in groups:
        p = sum(count*weights.get(run, 0) for run, count in pos.items())
        n = sum(count*weights.get(run, 0) for run, count in neg.items())
        favorable += p*(negatives+0.5*n)
        positives += p
        negatives += n
    return favorable/(positives*negatives) if positives and negatives else None


def summary(units, horizon, feature, bootstraps=2000, seed=20261122):
    binary = [u for u in units if u['classification'] in ('positive', 'negative')]
    totals = Counter(u['classification'] for u in binary)
    rows = [(u[horizon]['features'][feature]['maximum'], u['classification'], u['run_id'])
            for u in binary if u[horizon]['features'][feature]['maximum'] is not None]
    measured = Counter(row[1] for row in rows)
    runs = sorted(set(u['run_id'] for u in binary))
    groups = auc_groups(rows)
    point = weighted_auc(groups, dict.fromkeys(runs, 1))
    coverage = {key: measured[key]/totals[key] if totals[key] else None
                for key in ('positive', 'negative')}
    draws = []
    if point is not None:
        rng = random.Random(seed)
        for _ in range(bootstraps):
            weights = Counter(rng.choice(runs) for _ in runs)
            value = weighted_auc(groups, weights)
            if value is not None:
                draws.append(value)
    lower, upper = percentile(draws, .025), percentile(draws, .975)
    bands = {}
    for name, lo, hi in (('below48', 0, 48), ('48-59', 48, 60), ('60-71', 60, 72), ('72+', 72, 128)):
        bands[name] = {}
        for cls in ('positive', 'negative', 'continuing'):
            selected = [u for u in units if lo <= u['note'] < hi and u['classification'] == cls]
            values = [u[horizon]['features'][feature]['maximum'] for u in selected
                      if u[horizon]['features'][feature]['maximum'] is not None]
            bands[name][cls] = dict(total=len(selected), measured=len(values), median=percentile(values, .5))
    passed = (point is not None and point >= .90 and lower is not None and lower >= .80
              and all(value is not None and value >= .90 for value in coverage.values()))
    return dict(total=dict(totals), measured=dict(measured), coverage=coverage, auc=point,
                cluster_bootstrap_95=[lower, upper], valid_bootstraps=len(draws),
                design_bar=passed, bands=bands)


def analyze(lines, *, census, mask, expected_rows, bootstraps=2000):
    if next(lines, '').strip() != '# m3_quiet_cell_intervals_v1' or \
            next(lines, '').rstrip('\r\n').split('\t') != OUTPUT_HEADER:
        raise ValueError('Unexpected reduced-table header')
    units, original = make_units(census, mask)
    index = {}
    for u in units:
        index.setdefault((u['note'], u['run_id']), []).append(u)
    previous = (-1, -1)
    statuses, quiet, rows = Counter(), Counter(), 0
    for line in lines:
        cell, ids, status, features = parse_row(line.rstrip('\r\n').split('\t'))
        key = cell.sample, cell.note
        if key <= previous or cell.sample % 64 != 63:
            raise ValueError('Row order or decision sample grid differs')
        previous = key
        rows += 1
        statuses[status] += 1
        quiet[cell.quiet] += 1
        for wi in ids:
            if wi >= len(mask['marked_intervals']):
                raise ValueError('Unknown window ID')
            start, end = mask['marked_intervals'][wi]
            if not max(0, start-1920) <= cell.sample < min(mask['horizon'], end+9600):
                raise ValueError('Row outside declared reduction window')
            for u in index.get((cell.note, wi), []):
                for horizon in HORIZONS:
                    observe(u[horizon], cell.sample, cell.quiet, status, features)
                for label in u['labels']:
                    observe(label['measurements'], cell.sample, cell.quiet, status, features)
    if rows != expected_rows:
        raise ValueError('Reduced row count differs')
    stats = {horizon: {feature: summary(units, horizon, feature, bootstraps)
                       for feature in FEATURES} for horizon in HORIZONS}
    # Compare the measurement change on exactly the same observed pairs.
    paired = [u for u in units if all(u['by_25ms']['features'][f]['maximum'] is not None
              for f in ('interval_fundamental_share', 'raw_fundamental_share'))]
    paired_stats = {f: summary(paired, 'by_25ms', f, bootstraps)
                    for f in ('interval_fundamental_share', 'raw_fundamental_share')}
    a = paired_stats['interval_fundamental_share']
    b = paired_stats['raw_fundamental_share']
    gain = a['auc']-b['auc'] if a['auc'] is not None and b['auc'] is not None else None
    covered = sorted({r['label'] for u in units for r in u['labels']})
    expected_labels = sorted(census['positive_labels'])
    return dict(rows=rows, interval_status_counts=dict(statuses), quiet_counts=dict(quiet),
        original_span_classes=original, pairs=len(units),
        pair_classes=dict(Counter(u['classification'] for u in units)),
        expected_positive_labels=expected_labels, covered_positive_labels=covered,
        missing_positive_labels=sorted(set(expected_labels)-set(covered)),
        additional_positive_labels=sorted(set(covered)-set(expected_labels)),
        summaries=stats, paired_primary_comparison=paired_stats,
        primary_auc_gain_over_raw=gain,
        primary_supported=bool(stats['by_25ms']['interval_fundamental_share']['design_bar']
                               and gain is not None and gain >= .05),
        any_interval_design_bar=any(stats['by_25ms'][key]['design_bar'] for key in FEATURES[:3]),
        units=units, policy_change=False, promotion_accepted=False)
