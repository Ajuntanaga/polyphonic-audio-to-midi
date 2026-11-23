"""One frozen native-candidate classifier feasibility screen, GitHub CPU only."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import time

import numpy as np

from tools.basic_pitch_cached_diagnosis import labels_from_measurement
from tools.basic_pitch_temporal_reliability import calibration_cutoff, passage_split
from tools.candidate_outcome_analysis import _candidates
from tools.native_candidate_temporal import (CausalHistory, FEATURE_NAMES, MODEL_PARAMS,
    addition_spans, full_interval_targets)
from tools.pitch_detector_comparison import digest, score
from tools.portable_basic_pitch_cached_diagnosis import fetch_artifact, require_identity
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.portable_basic_pitch_temporal_reliability import evaluate_region


def parse_trace(lines, sample_count):
    """Read only causal columns; labels/matched/voices/floor_stats never accessed."""
    history, chunks, keys, buffer, coordinates = CausalHistory(), [], [], [], []
    header = None
    previous_tick = None
    ticks = 0
    counts = Counter()
    for line in lines:
        if line.startswith('#'):
            if ticks or line.strip() != '# m3_candidate_outcome_v5':
                raise ValueError('Expected v5 marker before data')
            continue
        if header is None:
            header = line.rstrip('\n').split('\t')
            if (header[:8] != ['sample', 'tick', 'quiet', 'signal_samples', 'labels',
                               'matched_labels', 'voices', 'candidates']
                    or header[8:] != ['input_power', 'floor_stats']):
                raise ValueError('Unexpected v5 columns')
            continue
        parts = line.rstrip('\n').split('\t')
        if len(parts) != len(header):
            raise ValueError('Invalid trace row width')
        sample, tick, quiet = map(int, parts[:3])
        if (sample != ticks*64+63 or sample >= sample_count
                or previous_tick is not None and tick != previous_tick+1):
            raise ValueError('Trace decision clock differs')
        previous_tick = tick
        candidates = _candidates({'candidate_text': parts[7]})
        if any('energy_observed' not in c for c in candidates.values()):
            raise ValueError('Expected all 47 native v4 tuple fields')
        rows = history.frame(tick, quiet, candidates, float(parts[8]))
        counts['serialized_rows'] += len(candidates)
        counts['eligible_rows'] += len(rows)
        counts['quiet_'+str(quiet)] += 1
        start, end = sample+1, min(sample+65, sample_count)
        if start < end:
            for note, features in rows:
                buffer.append(features)
                coordinates.append((start, end, note))
            if len(buffer) >= 8192:
                chunks.append(np.asarray(buffer, dtype=np.float32)); buffer = []
                keys.append(np.asarray(coordinates, dtype=np.int64)); coordinates = []
        ticks += 1
    if ticks != sample_count//64 or not chunks and not buffer:
        raise ValueError('Incomplete trace or no eligible observations')
    if buffer:
        chunks.append(np.asarray(buffer, dtype=np.float32))
        keys.append(np.asarray(coordinates, dtype=np.int64))
    features, coordinates = np.concatenate(chunks), np.concatenate(keys)
    return dict(features=features, starts=coordinates[:, 0], ends=coordinates[:, 1],
                notes=coordinates[:, 2], census=dict(counts, decision_ticks=ticks,
                retained_intervals=len(coordinates)))


def verified_data(name, config, baseline, cache):
    clock = dict(sample_count=config['sample_count'], sample_rate=config['sample_rate'])
    labels = labels_from_measurement(baseline['measurement'])
    require_identity(score(baseline['pitch_spans'], labels, **clock),
                     baseline['measurement'], name+' CURRENT complete score')
    sha = hashlib.sha256()
    with gzip.open(cache/config['trace_name'], 'rb') as stream:
        def lines():
            for raw in stream:
                sha.update(raw)
                yield raw.decode('utf-8')
        result = parse_trace(lines(), clock['sample_count'])
    require_identity(sha.hexdigest(), config['uncompressed_sha256'], name+' complete trace')
    result.update(clock=clock, labels=labels, current=baseline['pitch_spans'])
    result['target'] = full_interval_targets(result['starts'], result['ends'], result['notes'],
                                             labels, clock['sample_count'])
    return result


def diagnostic(data, probability, left, right, cutoff):
    from sklearn.metrics import roc_auc_score
    mask = (data['starts'] >= left) & (data['ends'] <= right)
    y, p = data['target'][mask], probability[mask]
    weights = data['ends'][mask]-data['starts'][mask]
    selected = p >= cutoff
    return dict(rows=len(y), genuine_rows=int(y.sum()), negative_rows=int((~y).sum()),
        admitted_genuine_rows=int((selected & y).sum()),
        admitted_negative_rows=int((selected & ~y).sum()),
        duration_weighted_auc=float(roc_auc_score(y, p, sample_weight=weights))
          if len(np.unique(y)) == 2 else None)


def run(spec_path, output):
    remote_only()  # Before any corpus parsing, downloads, fitting or inference.
    from sklearn.ensemble import HistGradientBoostingClassifier
    import sklearn
    import joblib
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache', 'bulk')}
    for p in folders.values(): p.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_native_candidate_temporal_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), installed_output_changed=False,
        promotion_accepted=False)
    try:
        spec = json.loads(spec_path.read_text())
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git', '-C', str(root), 'rev-parse', 'HEAD'])
        if (source != os.environ.get('SOURCE_SHA')
                or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']
                or sklearn.__version__ != '1.7.2' or spec['model_parameters'] != MODEL_PARAMS
                or spec['feature_names'] != FEATURE_NAMES):
            raise ValueError('Frozen source, feature/model or environment mismatch')
        report['provenance'] = dict(source_commit=source, worker_commit=os.environ['GITHUB_SHA'],
            run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
            worker_repository=os.environ['GITHUB_REPOSITORY'], specification=spec,
            specification_sha256=digest(spec_path), platform=platform.platform(),
            sklearn=sklearn.__version__, numpy=np.__version__)
        baseline_path = root/spec['baseline']['path']
        check_hash(baseline_path, spec['baseline']['sha256'])
        baseline = json.loads(baseline_path.read_text())
        report['stage'] = 'retrieve and parse pinned ordinary trace'
        save_json(report_path, report)
        ordinary_config = spec['datasets']['ordinary']
        report['artifacts'] = {'ordinary': fetch_artifact(spec['worker_repository'],
            ordinary_config['artifact'], folders['cache']/'ordinary', folders['logs'])}
        ordinary = verified_data('ordinary', ordinary_config,
            baseline['datasets']['ordinary'], folders['cache']/'ordinary')
        split = passage_split(ordinary['labels'], **ordinary['clock'], **spec['split'])
        require_identity(split['passage_count'], 131, 'ordinary passage count')
        report['split'] = split
        report['stage'] = 'fit one frozen native-feature model on training passages'
        report['ordinary_census'] = ordinary['census']
        save_json(report_path, report)
        left, right = split['regions']['train']
        train = (ordinary['starts'] >= left) & (ordinary['ends'] <= right)
        y = ordinary['target'][train]
        weights = (ordinary['ends'][train]-ordinary['starts'][train]).astype(float)
        positive, negative = float(weights[y].sum()), float(weights[~y].sum())
        if min(positive, negative) <= 0: raise ValueError('Both training classes required')
        weights[y] *= (positive+negative)/(2*positive)
        weights[~y] *= (positive+negative)/(2*negative)
        weights /= weights.mean()
        model = HistGradientBoostingClassifier(**MODEL_PARAMS)
        started = time.perf_counter()
        model.fit(ordinary['features'][train], y, sample_weight=weights)
        report['fit'] = dict(seconds=time.perf_counter()-started, rows=len(y),
            genuine_rows=int(y.sum()), negative_rows=int((~y).sum()),
            class_duration_samples=dict(genuine=positive, negative=negative))
        probability = model.predict_proba(ordinary['features'])[:, 1]
        left, right = split['regions']['calibration']
        calibration = (ordinary['starts'] >= left) & (ordinary['ends'] <= right)
        cutoff = calibration_cutoff(probability, ordinary['target'], calibration)
        report['cutoff'] = dict(value=cutoff, rule='nextafter(max negative calibration probability,+inf)',
                                test_tuned=False)
        joblib.dump(dict(model=model, feature_names=FEATURE_NAMES, cutoff=cutoff),
                    folders['bulk']/'frozen-model.joblib', compress=3)
        report['stage'] = 'model and cutoff frozen; evaluate both test partitions'
        save_json(report_path, report)
        report['datasets'] = {}
        for name in ('ordinary', 'extended-middle'):
            if name == 'ordinary': data = ordinary
            else:
                config = spec['datasets'][name]
                report['artifacts'][name] = fetch_artifact(spec['worker_repository'],
                    config['artifact'], folders['cache']/name, folders['logs'])
                data = verified_data(name, config, baseline['datasets'][name], folders['cache']/name)
                probability = model.predict_proba(data['features'])[:, 1]
            added = addition_spans(probability, cutoff, data['starts'], data['ends'],
                                   data['notes'], data['clock']['sample_count'])
            regions = split['regions'] if name == 'ordinary' else dict(test=(0, data['clock']['sample_count']))
            report['datasets'][name] = dict(census=data['census'],
                identities=dict(CURRENT_complete_score=True, complete_trace_hash=True),
                regions={part:evaluate_region(data, added, *bounds) for part,bounds in regions.items()},
                diagnostics={part:diagnostic(data, probability, *bounds, cutoff)
                             for part,bounds in regions.items()},
                full_record_descriptive=evaluate_region(data, added, 0, data['clock']['sample_count']))
            np.savez_compressed(folders['bulk']/(name+'-predictions.npz'),
                probability=probability, starts=data['starts'], ends=data['ends'], notes=data['notes'])
            with gzip.open(folders['bulk']/(name+'-addition-spans.json.gz'), 'wt') as stream:
                json.dump(dict(cutoff=cutoff, addition_spans=added), stream, separators=(',', ':'))
            save_json(report_path, report)
        test = report['datasets']['ordinary']['regions']['test']
        cal = report['datasets']['ordinary']['regions']['calibration']
        middle = report['datasets']['extended-middle']['regions']['test']
        gates = dict(calibration_no_false_growth=cal['comparison']['no_pitch_safety_regression'],
            ordinary_test_no_regression=test['comparison']['no_pitch_safety_regression'],
            ordinary_test_gain_at_least_1pp=test['comparison']['pitch_coverage_gain_pp'] >= 1,
            ordinary_test_at_least_5_gaining_labels=test['labels_gaining'] >= 5,
            middle_test_no_regression=middle['comparison']['no_pitch_safety_regression'])
        report.update(state='completed', final=True, stage='one fixed screen complete', gates=gates,
            feasibility_passed=all(gates.values()), decision='EXPLORATORY_PASS' if all(gates.values()) else 'REJECTED',
            limits=['Passage split is not source-take disjoint; both recordings are development data.',
                    'Eligibility excludes low-score/unformed/quiet candidates; no verdict about those rows.',
                    'Detector state is the original continuous replay; no feedback from added outputs.',
                    'Classifier overhead, strings, unison multiplicity, MIDI, allocation and deadline unmeasured.',
                    'No deployment or gate changes; a pass requires causal integration and new-recording testing.'])
        report['evidence'] = {p.name:dict(bytes=p.stat().st_size, sha256=digest(p))
                              for p in folders['bulk'].iterdir() if p.is_file()}
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        save_json(report_path, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', dest='spec_path', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    result = run(**vars(parser.parse_args()))
    print(json.dumps({key:result[key] for key in ('state', 'decision', 'gates')}))
