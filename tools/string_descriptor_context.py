#!/usr/bin/env python3
"""Compare frozen descriptor margins at matched pitch/string/fret geometry.

Annotation time, not candidate age, separates attack and sustain. Scores are
first summarized per annotation segment, so a long segment cannot masquerade
as many independent recordings. Different takes still confound musical context
with timbre/detuning: this is descriptive evidence, not a causal overlap test,
a held-out classifier result, or a change to MIDI output.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import heapq
import itertools

from tools.string_evidence_audit import AGE_BINS, OPEN_NOTES, age_bin
from tools.string_likelihood_decomposition import pair_margins


def matched_geometry(sources, max_fret):
    """Only annotation identities shared across the supplied recordings."""
    identities = []
    for source in sources:
        identities.append({(int(a['note']), int(a['mask']).bit_length() - 1)
                           for a in source['annotations']
                           if int(a['mask']).bit_count() == 1})
    common = set.intersection(*identities)
    return sorted((note, lane, other) for note, lane in common
                  if 0 <= note - OPEN_NOTES[lane] <= max_fret
                  for other in range(8) if other != lane and
                  0 <= note - OPEN_NOTES[other] <= max_fret)


def annotations(metadata):
    """Attach connected label episodes; overlapping chord labels stay together."""
    labels, episode, end = [], -1, -1
    seen = set()
    for original in sorted(metadata['annotations'], key=lambda a: (a['start'], a['index'])):
        a = {key: int(original[key]) for key in ('index', 'start', 'end', 'note', 'mask')}
        if (a['index'] in seen or not 0 <= a['start'] < a['end'] <= metadata['sample_count'] or
                not 0 <= a['note'] < 128 or not 0 <= a['mask'] < 256):
            raise ValueError('invalid annotation identity or bounds')
        seen.add(a['index'])
        if a['start'] >= end:
            episode += 1
        end = max(end, a['end'])
        a['episode'] = episode
        labels.append(a)
    return labels


def add_margins(counts, margins, row):
    counts['pairs'] += 1
    for term, value in margins.items():
        direction = 'positive' if value > 1e-9 else 'negative' if value < -1e-9 else 'tied'
        counts[term + '_' + direction] += 1
        counts[term + '_sum'] += value
    other = margins['total'] - margins['descriptor']
    counts['descriptor_reverses_correct_other_terms'] += int(other > 1e-9 and margins['total'] < -1e-9)
    counts['descriptor_rescues_wrong_other_terms'] += int(other < -1e-9 and margins['total'] > 1e-9)
    for key in ('isolated', 'phase_valid', 'beat_valid', 'fine_valid'):
        counts[key + '_rows'] += int(bool(int(row[key])))
    counts['selected_multiple_rows'] += int(int(row['selected_count']) > 1)


def summarize_segments(segments):
    if not segments:
        return None
    counts = Counter()
    for segment in segments:
        counts.update(segment['counts'])
    n = counts['pairs']
    return dict(segments=len(segments), episodes=len({s['episode'] for s in segments}),
                measured_pairs=n, counts=dict(counts),
                descriptor_negative_percent=100 * counts['descriptor_negative'] / n,
                equal_segment_descriptor_negative_percent=sum(
                    100 * s['counts'].get('descriptor_negative', 0) / s['counts']['pairs']
                    for s in segments) / len(segments),
                equal_segment_descriptor_margin=sum(
                    s['counts']['descriptor_sum'] / s['counts']['pairs']
                    for s in segments) / len(segments))


def analyze(rows, metadata, geometry):
    stride, samples = int(metadata['grid_stride_samples']), int(metadata['sample_count'])
    rate = int(metadata['sample_rate'])
    if stride <= 0 or rate <= 0 or metadata['sampled_frames'] != samples // stride:
        raise ValueError('incompatible complete capture grid')
    labels = annotations(metadata)
    targets = defaultdict(list)
    for note, lane, other in geometry:
        targets[(note, lane)].append(other)
    active, ends, cursor, row_count = {}, [], 0, 0
    groups = iter(itertools.groupby(rows, key=lambda row: int(row['sample'])))
    group = next(groups, None)
    coverage, buckets = Counter(), defaultdict(Counter)
    label_by_index = {a['index']: a for a in labels}
    for sample in range(stride - 1, samples, stride):
        while ends and ends[0][0] <= sample:
            _, index = heapq.heappop(ends)
            active.pop(index)
        while cursor < len(labels) and labels[cursor]['start'] <= sample:
            a = labels[cursor]
            cursor += 1
            if a['end'] > sample:
                active[a['index']] = a
                heapq.heappush(ends, (a['end'], a['index']))
        captured = {}
        if group is not None and group[0] < sample:
            raise ValueError('trace out of order or off grid')
        if group is not None and group[0] == sample:
            for row in group[1]:
                note = int(row['note'])
                if note in captured or not 0 <= note < 128 or int(row['tick']) * 64 - 1 != sample:
                    raise ValueError('duplicate note or incompatible clock')
                captured[note] = row
                row_count += 1
            group = next(groups, None)
        by_note = defaultdict(list)
        for a in active.values():
            by_note[a['note']].append(a)
        context = 'annotated_chord' if len(by_note) > 1 else 'annotated_single'
        for note, matching in by_note.items():
            # Overlapping same-pitch labels have ambiguous onset/segment identity.
            if len(matching) != 1:
                coverage['overlapping_same_pitch_targets_excluded'] += 1
                continue
            a = matching[0]
            if a['mask'].bit_count() != 1:
                continue
            lane = a['mask'].bit_length() - 1
            if (note, lane) not in targets:
                continue
            age = age_bin(sample - a['start'], rate)
            coverage[age + '_targets'] += 1
            if age == AGE_BINS[1]:
                continue
            row = captured.get(note)
            if row is None:
                coverage['missing_assignment_row'] += 1
                continue
            if not int(row['expected_note']) or int(row['expected_mask']) != a['mask']:
                raise ValueError('trace and annotation identity disagree')
            if int(row['posterior_observation_available']) and (
                    not int(row['observed']) or int(row['fixed_context'])):
                raise ValueError('likelihood contradicts current observation context')
            if not int(row['complete_calibration']) or not int(row['posterior_observation_available']):
                coverage['likelihood_unavailable'] += 1
                continue
            reserved = int(row['reserved_coasting']) | int(row['reserved_extras'])
            for other in targets[(note, lane)]:
                pair = (1 << lane) | (1 << other)
                if pair & reserved or pair & ~int(row['playable']):
                    coverage['reserved_or_infeasible_pair'] += 1
                    continue
                margins = pair_margins(row, lane, other)
                add_margins(buckets[(a['index'], other, age, context)], margins, row)
                coverage['measured_pairs'] += 1
    if group is not None or row_count != metadata['trace_rows']:
        raise ValueError('trace row accounting or bounds mismatch')
    segments = []
    for (index, other, age, context), counts in sorted(buckets.items()):
        a = label_by_index[index]
        lane = a['mask'].bit_length() - 1
        segments.append(dict(annotation=index, episode=a['episode'], start=a['start'], end=a['end'],
                             note=a['note'], lane=lane, fret=a['note'] - OPEN_NOTES[lane],
                             competitor=other, age=age, context=context, counts=dict(counts)))
    return dict(coverage=dict(coverage), segments=segments)


def compare(datasets):
    cells = defaultdict(lambda: defaultdict(list))
    for name, result in datasets.items():
        wanted = 'annotated_chord' if name == 'ordinary' else 'annotated_single'
        for s in result['segments']:
            if s['context'] == wanted:
                cells[(s['note'], s['lane'], s['competitor'], s['age'])][name].append(s)
    comparisons = []
    for (note, lane, other, age), cell in sorted(cells.items()):
        summaries = {name: summarize_segments(cell[name]) for name in datasets}
        ordinary, isolated = summaries['ordinary'], summaries['isolated-08']
        delta = None if ordinary is None or isolated is None else (
            ordinary['equal_segment_descriptor_negative_percent'] -
            isolated['equal_segment_descriptor_negative_percent'])
        comparisons.append(dict(note=note, lane=lane, fret=note - OPEN_NOTES[lane],
                                competitor=other, age=age, datasets=summaries,
                                ordinary_minus_isolated_negative_percentage_points=delta))
    return comparisons


def run(trace_paths, report):
    names = ('ordinary', 'isolated-08')
    sources = [report['datasets'][name] for name in names]
    if report.get('state') != 'completed' or not report.get('final'):
        raise ValueError('completed final capture required')
    for key in ('calibration_sha256', 'settings', 'sample_rate'):
        if sources[0]['provenance'][key] != sources[1]['provenance'][key]:
            raise ValueError('incompatible ' + key)
    geometry = matched_geometry([s['analysis'] for s in sources],
                                sources[0]['provenance']['settings']['max-fret'])
    datasets = {}
    for name, source in zip(names, sources):
        digest = hashlib.sha256()
        with gzip.open(trace_paths[name], 'rt', newline='') as handle:
            def lines():
                for line in handle:
                    digest.update(line.encode('utf-8'))
                    yield line
            result = analyze(csv.DictReader(lines(), delimiter='\t'), source['analysis'], geometry)
        if digest.hexdigest() != source['provenance']['trace_sha256']:
            raise ValueError('trace SHA-256 mismatch for ' + name)
        result['provenance'] = source['provenance']
        datasets[name] = result
    return dict(schema_version=1, source_run=report['run_id'], datasets=datasets,
                geometry=geometry, comparisons=compare(datasets),
                capture_binary_sha256=report['binary_sha256'],
                capture_source_files_sha256=report['source_files_sha256'],
                interpretation=__doc__, installed_changed=False,
                held_out_gain_measured=False, causal_overlap_measured=False)
