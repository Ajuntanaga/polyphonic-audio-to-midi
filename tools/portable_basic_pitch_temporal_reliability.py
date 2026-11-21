"""One fixed learned temporal-reliability screen on saved arrays, GitHub CPU only."""
import argparse
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import platform
import sys
import time

import numpy as np

from tools.basic_pitch_cached_diagnosis import decode_cached, labels_from_measurement
from tools.basic_pitch_streaming import SETTINGS, emission_spans
from tools.basic_pitch_temporal_reliability import (MODEL_PARAMS, calibration_cutoff,
    causal_features, decision_intervals, full_interval_targets, occupancy_spans,
    passage_split, region_inputs)
from tools.pitch_detector_comparison import compare, digest, score, union_spans
from tools.portable_basic_pitch_cached_diagnosis import (cached_arrays, fetch_artifact,
    require_identity)
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json


def verified_dataset(name, config, baseline, reference, cache):
    clock = dict(sample_count=config['sample_count'], sample_rate=config['sample_rate'])
    labels = labels_from_measurement(baseline['measurement'])
    require_identity(score(baseline['pitch_spans'], labels, **clock),
                     baseline['measurement'], name+' CURRENT complete score')
    arrays = cached_arrays(cache/(name+'-stream.npz'), stream=True)
    event_doc = json.loads((cache/(name+'-events.json')).read_text())
    require_identity(event_doc['frame_columns'],
        ['frame', 'nominal_model_sample', 'window_end_exclusive', 'arrived_source_samples'], 'frame columns')
    require_identity(event_doc['timing_columns'],
        ['source_end', 'arrival_ns', 'service_ns', 'finish_ns', 'queued_ns',
         'resample_and_buffer_ns', 'model_ns', 'decode_ns', 'model_called'], 'timing columns')
    events, opened = decode_cached(arrays['note'], arrays['onset'])
    require_identity(opened, event_doc['cleanup']['notes'], name+' EOF state')
    clocks = {int(row[0]): row for row in arrays['timing']}
    reconstructed = []
    for event in events:
        row = arrays['frames'][event['frame']]
        timing = clocks[int(row[3])]
        reconstructed.append(dict(event, available_ns=int(timing[1]), emitted_ns=int(timing[3])))
    require_identity(reconstructed, event_doc['events'], name+' complete events/clocks')
    emitted, audit = emission_spans(reconstructed, 'emitted_ns', clock['sample_count'])
    require_identity(score(emitted, labels, **clock), reference['measurement'], name+' A full score')
    indices, starts, ends = decision_intervals(arrays['frames'], arrays['timing'], **clock)
    target = full_interval_targets(starts, ends, labels, clock['sample_count'])
    return dict(clock=clock, labels=labels, current=baseline['pitch_spans'],
        arrays=arrays, indices=indices, starts=starts, ends=ends, target=target,
        identity=dict(current_complete_score=True, A_complete_score=True,
                      complete_events_and_clocks=True, EOF_state=True), event_audit=audit)


def evaluate_region(data, added, left, right):
    clock = dict(sample_count=right-left, sample_rate=data['clock']['sample_rate'])
    union = union_spans(data['current']+added, sample_count=data['clock']['sample_count'])
    current, labels, mapping = region_inputs(data['current'], data['labels'], left, right)
    candidate, _, _ = region_inputs(union, data['labels'], left, right)
    reference, measured = score(current, labels, **clock), score(candidate, labels, **clock)
    comparison = compare(reference, measured)
    # This is occupancy by union, not a MIDI hand-off or attack/release test.
    if any(min(r['present_samples_delta'], r['longest_present_samples_delta']) < 0
           for r in comparison['label_deltas']):
        raise ValueError('Union lost CURRENT occupancy')
    return dict(source_region=[left, right], original_label_indices=mapping,
        current_measurement=reference, candidate_measurement=measured,
        comparison=comparison,
        labels_gaining=sum(r['present_samples_delta'] > 0 for r in comparison['label_deltas']),
        occupancy_segments=dict(current=len(current), candidate=len(candidate)),
        raw_midi_lifecycle='Not measured: these merged occupancy spans are not delivered MIDI.')


def probability_diagnostic(probability, target, starts, ends, left, right, cutoff):
    from sklearn.metrics import roc_auc_score
    duration = np.maximum(0, np.minimum(ends, right)-np.maximum(starts, left))
    mask = duration > 0
    y, p = target[mask].ravel(), probability[mask].ravel()
    weight = np.repeat(duration[mask], 88)
    chosen = p >= cutoff
    return dict(interval_pitch_rows=len(y), positive_rows=int(y.sum()),
        negative_rows=int((~y).sum()), admitted_positive_rows=int((chosen & y).sum()),
        admitted_negative_rows=int((chosen & ~y).sum()),
        duration_weighted_auc=float(roc_auc_score(y, p, sample_weight=weight))
            if len(np.unique(y)) == 2 else None,
        caveat='Diagnostic only; full-interval target treats every partial-label interval as negative. '
               'This statistic cannot change the frozen cutoff or acceptance gates.')


def verify_purges(data, split):
    bounds = {}
    prior_end = split['regions']['train'][1]
    for name in ('calibration', 'test'):
        left, right = split['regions'][name]
        rows = np.flatnonzero((data['starts'] < right) & (data['ends'] > left))
        first_index = int(data['indices'][rows[0]])
        oldest = max(0, first_index-16)
        # Conservatively include the complete 1.988s model window of the oldest
        # feature row plus one 640-source-sample resampler history block.
        source_begin = ((int(data['arrays']['frames'][oldest, 2])-SETTINGS['model_samples'])
                        *SETTINGS['source_rate']//SETTINGS['model_rate']-640)
        if source_begin < prior_end:
            raise ValueError('Model/feature context crosses a fitted partition boundary')
        bounds[name] = dict(earliest_context_source_sample=source_begin,
                            prior_partition_end=prior_end, disjoint=True)
        prior_end = split['regions']['calibration'][1]
    return bounds


def run(spec_path, output):
    remote_only()  # Before recorded-cache access, classifier fitting or downloads.
    from sklearn.ensemble import HistGradientBoostingClassifier
    import sklearn
    import joblib
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache', 'bulk')}
    for folder in folders.values():
        folder.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_temporal_reliability_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), installed_output_changed=False,
        inference_performed=False, promotion_accepted=False)
    try:
        spec = json.loads(spec_path.read_text())
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git', '-C', str(root), 'rev-parse', 'HEAD'])
        if (source != os.environ.get('SOURCE_SHA')
                or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']
                or spec['streaming_settings'] != SETTINGS or spec['model_parameters'] != MODEL_PARAMS
                or sklearn.__version__ != '1.7.2'):
            raise ValueError('Frozen source, environment or configuration mismatch')
        require_identity(spec['datasets'], {
            'ordinary': dict(sample_count=10689600, sample_rate=96000),
            'extended-middle': dict(sample_count=2241600, sample_rate=96000),
        }, 'frozen datasets and sample clocks')
        report['provenance'] = dict(source_commit=source, worker_commit=os.environ['GITHUB_SHA'],
            run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
            worker_repository=os.environ['GITHUB_REPOSITORY'], specification=spec,
            specification_sha256=digest(spec_path), python=sys.version,
            platform=platform.platform(), sklearn=sklearn.__version__, numpy=np.__version__)
        references = {}
        for name, pin in spec['references'].items():
            path = root/pin['path']
            check_hash(path, pin['sha256'])
            references[name] = json.loads(path.read_text())
        report['stage'] = 'retrieve pinned dense activations'
        save_json(report_path, report)
        report['artifact'] = fetch_artifact(spec['worker_repository'], spec['artifact'],
                                           folders['cache']/'stream', folders['logs'])
        data = {name: verified_dataset(name, config, references['baseline']['datasets'][name],
                    references['stream']['datasets'][name], folders['cache']/'stream')
                for name, config in spec['datasets'].items()}
        report['identities'] = {name: row['identity'] for name, row in data.items()}
        ordinary = data['ordinary']
        split = passage_split(ordinary['labels'], **ordinary['clock'], **spec['split'])
        if split['passage_count'] != 131:
            raise ValueError('Frozen corpus passage count differs')
        report['split'] = split
        report['context_purges'] = verify_purges(ordinary, split)
        report['stage'] = 'fit one frozen model on training passages only'
        save_json(report_path, report)
        features, names = causal_features(ordinary['arrays']['note'], ordinary['arrays']['onset'])
        features = features[ordinary['indices']]
        report['feature_names'] = names
        train_left, train_right = split['regions']['train']
        train = (ordinary['starts'] >= train_left) & (ordinary['ends'] <= train_right)
        y = ordinary['target'][train].ravel()
        weights = np.repeat(ordinary['ends'][train]-ordinary['starts'][train], 88).astype(float)
        positive_duration, negative_duration = float(weights[y].sum()), float(weights[~y].sum())
        if min(positive_duration, negative_duration) <= 0:
            raise ValueError('Both training classes required')
        total = positive_duration+negative_duration
        weights[y] *= total/(2*positive_duration)
        weights[~y] *= total/(2*negative_duration)
        weights /= weights.mean()
        model = HistGradientBoostingClassifier(**MODEL_PARAMS)
        started = time.perf_counter()
        model.fit(features[train].reshape(-1, len(names)), y, sample_weight=weights)
        report['fit'] = dict(seconds=time.perf_counter()-started, rows=len(y),
            positive_rows=int(y.sum()), negative_rows=int((~y).sum()),
            positive_duration=positive_duration, negative_duration=negative_duration,
            weights='Duration weighted, equal total weight for each class, mean weight 1.')
        probabilities = model.predict_proba(features.reshape(-1, len(names)))[:, 1].reshape(-1, 88)
        cal_left, cal_right = split['regions']['calibration']
        calibration = (ordinary['starts'] < cal_right) & (ordinary['ends'] > cal_left)
        cutoff = calibration_cutoff(probabilities, ordinary['target'], calibration)
        report['cutoff'] = dict(value=cutoff,
            rule='nextafter(max probability of any negative calibration interval, +infinity)',
            tuned_on_test=False, all_admissions_blocked=cutoff > 1)
        # Persist model/cutoff before evaluating either test partition.
        joblib.dump(dict(model=model, feature_names=names, cutoff=cutoff),
                    folders['bulk']/'frozen-model.joblib', compress=3)
        report['stage'] = 'frozen model and cutoff; evaluate held-out partitions'
        save_json(report_path, report)
        report['datasets'] = {}
        for name in ('ordinary', 'extended-middle'):
            row = data[name]
            if name != 'ordinary':
                features, other_names = causal_features(row['arrays']['note'], row['arrays']['onset'])
                require_identity(other_names, names, 'feature order')
                features = features[row['indices']]
                probabilities = model.predict_proba(features.reshape(-1, len(names)))[:, 1].reshape(-1, 88)
            added = occupancy_spans(probabilities, cutoff, row['starts'], row['ends'],
                                    row['clock']['sample_count'])
            regions = split['regions'] if name == 'ordinary' else dict(test=(0, row['clock']['sample_count']))
            results = {part: evaluate_region(row, added, *bounds) for part, bounds in regions.items()}
            diagnostics = {part: probability_diagnostic(probabilities, row['target'],
                row['starts'], row['ends'], *bounds, cutoff) for part, bounds in regions.items()}
            report['datasets'][name] = dict(regions=results, probability_diagnostics=diagnostics,
                full_record_descriptive=evaluate_region(row, added, 0, row['clock']['sample_count']),
                original_event_audit=row['event_audit'])
            evidence = folders['bulk']/(name+'-predictions.npz')
            np.savez_compressed(evidence, probability=probabilities, starts=row['starts'],
                                ends=row['ends'], frame_indices=row['indices'])
            spans_path = folders['bulk']/(name+'-addition-spans.json.gz')
            with gzip.open(spans_path, 'wt', encoding='utf-8') as stream:
                json.dump(dict(cutoff=cutoff, addition_spans=added), stream, separators=(',', ':'))
            save_json(report_path, report)
        ordinary_test = report['datasets']['ordinary']['regions']['test']
        middle_test = report['datasets']['extended-middle']['regions']['test']
        cal = report['datasets']['ordinary']['regions']['calibration']
        gates = dict(calibration_no_false_growth=cal['comparison']['no_pitch_safety_regression'],
            ordinary_test_no_regression=ordinary_test['comparison']['no_pitch_safety_regression'],
            ordinary_test_gain_at_least_1pp=ordinary_test['comparison']['pitch_coverage_gain_pp'] >= 1.0,
            ordinary_test_at_least_5_gaining_labels=ordinary_test['labels_gaining'] >= 5,
            middle_test_no_regression=middle_test['comparison']['no_pitch_safety_regression'])
        report.update(state='completed', final=True, stage='one frozen screen complete',
            gates=gates, feasibility_passed=all(gates.values()),
            decision='exploratory pass; new-recording verification required' if all(gates.values())
                     else 'rejected; do not retune this screen',
            limits=['Source takes recur across mixtures; passage split is not source-disjoint.',
                    'Output uses measured historical FIFO completions but excludes new classifier overhead.',
                    'No string assignment, unison multiplicity, delivered hybrid MIDI, allocation or deadline test.',
                    'Full-record/train scores are descriptive and cannot substitute for test gates.',
                    'No installed change or promotion; positive result only justifies a new-recording test.'])
        report['evidence'] = {p.name: dict(bytes=p.stat().st_size, sha256=digest(p))
                              for p in folders['bulk'].iterdir() if p.is_file()}
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_or_updated_at'] = datetime.now(timezone.utc).isoformat()
        save_json(report_path, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', dest='spec_path', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    result = run(**vars(parser.parse_args()))
    print(json.dumps(dict(state=result['state'], decision=result['decision'], gates=result['gates'])))
