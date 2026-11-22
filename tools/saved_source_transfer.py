"""Describe singleton/mixed errors in pinned predictions; never load audio/models."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import numpy as np

from tools.spectral_ablation_ranking import counts, digest


ROLES = {1: 'train', 2: 'calibration', 3: 'test'}
STATUSES = ('unknown', 'never_exact', 'sometimes_exact', 'always_exact_observed')


def source_index(manifest, consistency):
    checked = {r['source_key']: r for r in consistency['sources']}
    result = {}
    for file in manifest['files']:
        for take in file['takes']:
            key = file['stem'] + ':' + str(take['label_index'])
            if key in result:
                raise ValueError('Duplicate source key')
            row = dict(take, source_key=key, stem=file['stem'],
                       role=ROLES[take['calibration_pass']])
            status = checked.get(key)
            if status and (status['role'] != row['role'] or
                           status['label_note'] != row['midi_note'] or
                           status['string_mask'] != row['string_mask']):
                raise ValueError('Consistency source identity differs')
            row['consistency_status'] = (status['status'] if status else
                consistency['default_status_for_unlisted_sources'])
            result[key] = row
    if set(checked) - set(result):
        raise ValueError('Unknown consistency source')
    return result


def scheduled_pair_key(component, row):
    return (component['source_key'], component['crop_begin'], component['crop_end'],
            float(component['gain_db']) + float(row['gain_db']))


def diagnose(probability, truth, plan, cutoff, sources, role, note_low=32):
    probability, truth = np.asarray(probability), np.asarray(truth)
    if (probability.ndim != 2 or probability.shape != truth.shape or
            truth.dtype != np.dtype(bool) or len(plan) != len(truth) or
            not np.isfinite(probability).all() or (probability < 0).any() or
            (probability > 1).any() or not 0 < cutoff <= 1):
        raise ValueError('Invalid saved arrays or cutoff')
    pred = probability >= cutoff
    missing, extra = truth & ~pred, ~truth & pred
    exact = (truth == pred).all(axis=1)
    polyphony = truth.sum(axis=1)
    n_components = np.array([len(r['components']) for r in plan])
    selected_sources = {k: v for k, v in sources.items() if v['role'] == role}
    rows = {key: dict(role=role, source_key=key, stem=s['stem'],
        midi_note=s['midi_note'], string_mask=s['string_mask'],
        calibration_pass=s['calibration_pass'], consistency_status=s['consistency_status'],
        singleton_n=0, singleton_target_miss_n=0, singleton_exact_fail_n=0,
        singleton_fp_cells=0, singleton_false_notes={},
        mixed_occurrence_n=0, mixed_exact_fail_exposure_n=0,
        mixed_unison_occurrence_n=0, mixed_unique_pitch_by_cardinality={})
        for key, s in selected_sources.items()}
    usage, singleton_pairs = Counter(), defaultdict(list)
    for i, row in enumerate(plan):
        if row['example'] != i or row['role'] != role:
            raise ValueError('Plan ordering or role mismatch')
        if not np.isfinite(row['gain_db']):
            raise ValueError('Invalid scheduled gain')
        components = row['components']
        if len({c['string_mask'] for c in components}) != len(components):
            raise ValueError('Repeated string in mixture')
        notes = set()
        for c in components:
            key = c['source_key']
            if key not in selected_sources:
                raise ValueError('Source role isolation failed')
            s = selected_sources[key]
            if (c['stem'] != s['stem'] or c['note'] != s['midi_note'] or
                    c['string_mask'] != s['string_mask'] or
                    not s['start_sample'] <= c['crop_begin'] < c['crop_end'] <= s['end_sample'] or
                    c['crop_end'] - c['crop_begin'] != 16384 or
                    not np.isfinite(c['gain_db'])):
                raise ValueError('Source component identity differs')
            usage[key] += 1
            notes.add(c['note'])
        if notes != set((np.flatnonzero(truth[i]) + note_low).tolist()):
            raise ValueError('Plan targets differ from saved targets')
        if len(components) == 1:
            c = components[0]
            out = rows[c['source_key']]
            out['singleton_n'] += 1
            out['singleton_target_miss_n'] += int(missing[i].sum())
            out['singleton_exact_fail_n'] += int(not exact[i])
            out['singleton_fp_cells'] += int(extra[i].sum())
            for note in (np.flatnonzero(extra[i]) + note_low).tolist():
                k = str(note)
                out['singleton_false_notes'][k] = out['singleton_false_notes'].get(k, 0) + 1
            singleton_pairs[scheduled_pair_key(c, row)].append(i)
    if set(usage) != set(selected_sources):
        raise ValueError('Not every original source is represented')
    for out in rows.values():
        n, failures = out['singleton_n'], out['singleton_exact_fail_n']
        out['singleton_status'] = ('unknown' if not n else 'never_exact' if failures == n
            else 'sometimes_exact' if failures else 'always_exact_observed')
        out['singleton_false_pitch_opportunities'] = (truth.shape[1] - 1) * n

    def target_counter():
        return dict(expected=0, missing=0)

    target_strata = {name: defaultdict(target_counter) for name in
                     ('singleton_status', 'pitch_band', 'relative_scheduled_gain_db')}
    groups = {k: [] for k in ('all_sources_exact_alone', 'some_singleton_error',
                              'otherwise_unknown')}
    paired = dict(mixed_unique_pitch_targets=0, matching_singleton_observations=0,
                  targets_with_match=0, mixed_misses_with_match=0,
                  mixed_missing_despite_all_matched_singletons_found=0)
    unison_targets = target_counter()
    for i, row in enumerate(plan):
        components = row['components']
        if len(components) <= 1:
            continue
        statuses = [rows[c['source_key']]['singleton_status'] for c in components]
        group = ('some_singleton_error' if any(s in ('never_exact', 'sometimes_exact')
            for s in statuses) else 'otherwise_unknown' if 'unknown' in statuses
            else 'all_sources_exact_alone')
        groups[group].append(i)
        by_note = defaultdict(list)
        for c in components:
            by_note[c['note']].append(c)
            out = rows[c['source_key']]
            out['mixed_occurrence_n'] += 1
            out['mixed_exact_fail_exposure_n'] += int(not exact[i])
        max_gain = max(c['gain_db'] for c in components)
        for note, owners in by_note.items():
            miss = int(missing[i, note-note_low])
            if len(owners) > 1:
                unison_targets['expected'] += 1
                unison_targets['missing'] += miss
                status = 'unison_multiple_sources'
                for c in owners:
                    rows[c['source_key']]['mixed_unison_occurrence_n'] += 1
            else:
                c = owners[0]
                out = rows[c['source_key']]
                status = out['singleton_status']
                key = str(int(polyphony[i]))
                bucket = out['mixed_unique_pitch_by_cardinality'].setdefault(key, target_counter())
                bucket['expected'] += 1
                bucket['missing'] += miss
                matches = singleton_pairs.get(scheduled_pair_key(c, row), [])
                paired['mixed_unique_pitch_targets'] += 1
                paired['matching_singleton_observations'] += len(matches)
                paired['targets_with_match'] += int(bool(matches))
                paired['mixed_misses_with_match'] += int(bool(matches) and miss)
                paired['mixed_missing_despite_all_matched_singletons_found'] += int(
                    bool(matches) and miss and all(pred[m, note-note_low] for m in matches))
            band = '<48' if note < 48 else '48-59' if note < 60 else '60-71' if note < 72 else '72-84'
            gain = str(float(max(c['gain_db'] for c in owners) - max_gain))
            for dimension, key in [('singleton_status', status), ('pitch_band', band),
                                   ('relative_scheduled_gain_db', gain)]:
                bucket = target_strata[dimension][key]
                bucket['expected'] += 1
                bucket['missing'] += miss

    def measure(where):
        mask = np.zeros(len(plan), bool)
        mask[where] = True
        result = counts(probability[mask], truth[mask], cutoff)
        hm, he = missing[mask].any(axis=1), extra[mask].any(axis=1)
        result.update(missing_only=int((hm & ~he).sum()), extra_only=int((~hm & he).sum()),
                      both=int((hm & he).sum()))
        return result

    status_summary = {}
    for status in STATUSES:
        members = [r for r in rows.values() if r['singleton_status'] == status]
        status_summary[status] = dict(sources=len(members), singleton_n=sum(r['singleton_n'] for r in members),
            singleton_target_miss_n=sum(r['singleton_target_miss_n'] for r in members),
            singleton_exact_fail_n=sum(r['singleton_exact_fail_n'] for r in members),
            singleton_fp_cells=sum(r['singleton_fp_cells'] for r in members))
    summary = dict(frozen=measure(np.arange(len(plan))),
        silence=measure(np.flatnonzero(n_components == 0)),
        singleton=measure(np.flatnonzero(n_components == 1)),
        mixed=measure(np.flatnonzero(n_components > 1)),
        mixed_one_distinct_pitch=measure(np.flatnonzero((n_components > 1) & (polyphony == 1))),
        source_count=len(rows), source_usage=dict(usage), sources_by_singleton_status=status_summary,
        mixed_example_groups={k: measure(np.array(v, dtype=int)) for k, v in groups.items()},
        mixed_target_strata={k: dict(v) for k, v in target_strata.items()},
        mixed_unison_targets=unison_targets, scheduled_crop_level_matches=paired,
        by_distinct_pitch_count={str(n): measure(np.flatnonzero(polyphony == n))
                                for n in sorted(set(polyphony.tolist()))})
    mixed_counts = summary['mixed']
    if (sum(r['examples'] for r in summary['mixed_example_groups'].values()) != mixed_counts['examples'] or
            sum(r['false_negative'] for r in summary['mixed_example_groups'].values()) != mixed_counts['false_negative'] or
            sum(r['false_positive'] for r in summary['mixed_example_groups'].values()) != mixed_counts['false_positive']):
        raise ValueError('Mixed example groups do not reconcile')
    for strata in target_strata.values():
        if (sum(r['expected'] for r in strata.values()) != mixed_counts['expected'] or
                sum(r['missing'] for r in strata.values()) != mixed_counts['false_negative']):
            raise ValueError('Mixed target groups do not reconcile')
    unique = [b for r in rows.values() for b in r['mixed_unique_pitch_by_cardinality'].values()]
    if (sum(b['expected'] for b in unique) + unison_targets['expected'] != mixed_counts['expected'] or
            sum(b['missing'] for b in unique) + unison_targets['missing'] != mixed_counts['false_negative']):
        raise ValueError('Unique and unison targets do not reconcile')
    return summary, [rows[k] for k in sorted(rows)]


def verify_original(summary, probability, truth, cutoff, original):
    groups = [(summary['frozen'], original['summary']['overall'])]
    groups.extend((summary['by_distinct_pitch_count'][n], row)
                  for n, row in original['summary']['by_distinct_pitch_count'].items())
    for actual, before in groups:
        for field in ('examples', 'true_positive', 'false_positive', 'false_negative'):
            if actual[field] != before[field]:
                raise ValueError('Original count mismatch: ' + field)
        if actual['complete_sets'] != round(before['exact_set_percent'] * before['examples'] / 100):
            raise ValueError('Original complete-set mismatch')
    pred = probability >= cutoff
    for row in original['summary']['per_note']:
        j = row['note'] - 32
        measured = dict(support=int(truth[:, j].sum()),
            true_positive=int((pred[:, j] & truth[:, j]).sum()),
            false_positive=int((pred[:, j] & ~truth[:, j]).sum()),
            false_negative=int((~pred[:, j] & truth[:, j]).sum()))
        if any(row[k] != v for k, v in measured.items()):
            raise ValueError('Original per-note mismatch')
    if summary['source_usage'] != original['source_take_uses']:
        raise ValueError('Original source-use mismatch')
    if summary['silence']['false_positive'] != original['summary']['silence_false_predictions']:
        raise ValueError('Original silence mismatch')


def run(report_path, evidence, sources_path, consistency_path, output):
    report = json.loads(report_path.read_text())
    references = report['provenance']['specification']['references']
    for path, key in [(sources_path, 'sources'), (consistency_path, 'source_consistency')]:
        if digest(path) != references[key]['sha256']:
            raise ValueError('Reference pin mismatch: ' + key)
    sources = source_index(json.loads(sources_path.read_text()), json.loads(consistency_path.read_text()))
    roles, all_rows, hashes = {}, [], {p.name: digest(p) for p in (report_path, sources_path, consistency_path)}
    cutoff = report['cutoff_fit']['cutoff']
    for role, size in [('train', 16384), ('calibration', 4096), ('test', 4096)]:
        prediction, plan_path = evidence/(role+'-predictions.npz'), evidence/(role+'-mixture-plan.json.gz')
        for p in (prediction, plan_path):
            pin = report['evidence'][p.name]
            hashes[p.name] = digest(p)
            if p.stat().st_size != pin['bytes'] or hashes[p.name] != pin['sha256']:
                raise ValueError('Evidence pin mismatch: ' + p.name)
        with np.load(prediction, allow_pickle=False) as saved:
            if set(saved.files) != {'probability', 'targets', 'cutoff'}:
                raise ValueError('Unexpected prediction arrays')
            probability, truth = saved['probability'], saved['targets']
            if probability.shape != (size, 53) or float(saved['cutoff']) != cutoff:
                raise ValueError('Saved shape/cutoff mismatch')
        with gzip.open(plan_path, 'rt') as handle:
            plan = json.load(handle)
        summary, rows = diagnose(probability, truth, plan, cutoff, sources, role)
        verify_original(summary, probability, truth, cutoff, report['mixtures'][role])
        if summary['source_count'] != report['source_roles']['counts'][role]:
            raise ValueError('Source count mismatch')
        roles[role] = summary
        all_rows.extend(rows)
    if len(all_rows) != 555 or {r['source_key'] for r in all_rows} != set(sources):
        raise ValueError('Original source coverage mismatch')
    output.mkdir(parents=True, exist_ok=False)
    source_table = output/'sources.json'
    source_table.write_text(json.dumps(all_rows, indent=2, allow_nan=False)+'\n')
    result = dict(schema='m3_saved_source_transfer_v1', final=True,
        created_at=datetime.now(timezone.utc).isoformat(),
        run_id=report['provenance']['run_id'], source_commit=report['provenance']['source_commit'],
        original_decision=report['decision'], frozen_cutoff=cutoff, identities_passed=True,
        all_555_sources_retained=True, input_hashes=hashes,
        analysis_script_sha256=digest(__file__), sources_table_sha256=digest(source_table), roles=roles,
        limits=['Singleton status describes sampled crops/levels only; no causal mixture attribution.',
                'Missing singleton coverage is unknown. Multi-component unisons are separate.',
                'Mixed exact-failure exposures are non-additive and cannot attribute extra pitches.',
                'Source-consistency status never filters any example or score.',
                'Roles have been used for development; pass/protocol/content remain confounded.',
                'No audio/model/fit, timing, host, string assignment or installed-output measurement.'])
    (output/'report.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({role: {k: value[k] for k in ('singleton', 'mixed',
        'sources_by_singleton_status', 'scheduled_crop_level_matches')} for role, value in roles.items()}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('report', 'evidence', 'sources', 'consistency', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    run(args.report, args.evidence, args.sources, args.consistency, args.output)
