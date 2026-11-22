"""One exact-model ORT graph-optimization comparison on GitHub CPU.

No conversion, fitting, decoder change or policy selection. Both graph modes
run on the same worker; old disabled-ORT and corrected-TF tapes are references.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

import numpy as np

from tools.basic_pitch_onnx_export import compare_outputs, compare_streams
from tools.basic_pitch_streaming import SETTINGS
from tools.pitch_detector_comparison import compare, digest, read_labels, score
from tools.portable_basic_pitch_cached_diagnosis import require_identity
from tools.portable_basic_pitch_comparison import check_hash, remote_only, save_json
from tools.portable_basic_pitch_onnx_export import collect_reference
from tools.portable_basic_pitch_streaming import measure, StreamingBackend
from tools.portable_basic_pitch_trainability import synthetic_inputs
from tools.portable_direct_spectrum_learning import fetch_release


def validate_spec(spec):
    if (spec['streaming'] != SETTINGS or spec['max_absolute'] != 1e-4
            or spec['graph_modes'] != ['disabled', 'all']
            or spec['onnxruntime_version'] != '1.20.1'
            or set(spec['datasets']) != {'ordinary', 'extended-middle'}
            or spec['service_p99_limit_ns'] != 20_000_000
            or spec['queue_max_limit_ns'] != 26_666_667):
        raise ValueError('Frozen graph-optimization specification differs')


def compare_tapes(before, after, before_events, after_events, tolerance):
    with np.load(before, allow_pickle=False) as a, np.load(after, allow_pickle=False) as b:
        row = compare_streams(a, b, json.loads(before_events.read_text()),
                              json.loads(after_events.read_text()), tolerance)
        row['bit_identical_probabilities_and_source_frames'] = all(
            np.array_equal(a[key], b[key]) for key in ('note', 'onset', 'frames'))
        return row


def runtime_gates(timing):
    return dict(service_p99_under_20ms=timing['inference_block_service_ns']['p99'] <= 20_000_000,
                queue_max_under_26_667ms=timing['queued_before_service_ns']['maximum'] <= 26_666_667)


def assess(datasets, synthetic_pass):
    pairs = [row for dataset in datasets.values() for row in dataset['weights'].values()]
    integrity = bool(pairs) and all(row['disabled_reference_parity']['parity_pass'] for row in pairs)
    parity = bool(pairs) and all(row['optimized_vs_disabled']['parity_pass']
        and row['optimized_vs_corrected_tensorflow']['parity_pass'] for row in pairs)
    content = bool(pairs) and all(row['source_availability_scores_identical'] for row in pairs)
    timing = bool(pairs) and all(all(runtime_gates(row['all']['timing']).values()) for row in pairs)
    return dict(reference_reproduction_pass=integrity, optimized_backend_parity_pass=parity,
        source_availability_content_identical=content, optimized_cpu_feasibility_pass=timing,
        runtime_change_screen_pass=synthetic_pass and integrity and parity and content and timing,
        prior_adaptation_quality_pass=False, promotion_accepted=False, installed_output_changed=False,
        interpretation='Same weights, two ORT modes on one worker. CPU feasibility and backend parity only; '
            'prior label/false-output/held-out failures persist. No native callback, allocation or hardware proof.')


def run(spec_path, output):
    remote_only()
    spec = json.loads(spec_path.read_text())
    validate_spec(spec)
    source = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True,
                            text=True, check=True).stdout.strip()
    if source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
        raise ValueError('Dispatch/source mismatch')
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache', 'inputs', 'reference', 'bulk')}
    for path in folders.values():
        path.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_basic_pitch_graph_optimization_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), source_commit=source,
        worker_commit=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
        run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], specification=spec,
        specification_sha256=digest(spec_path), installed_output_changed=False,
        promotion_accepted=False, live_readiness='not measured', models={}, datasets={})
    save_json(report_path, report)
    start = time.perf_counter()
    try:
        import onnxruntime as ort
        if ort.__version__ != spec['onnxruntime_version']:
            raise ValueError('ORT version differs')
        report['environment'] = dict(python=sys.version, platform=platform.platform(),
            numpy=np.__version__, onnxruntime=ort.__version__, intra_threads=2, inter_threads=1)
        root = Path(__file__).resolve().parents[1]
        baseline_pin = spec['baseline']
        check_hash(root/baseline_pin['path'], baseline_pin['sha256'])
        baseline = json.loads((root/baseline_pin['path']).read_text())
        references = collect_reference(spec, folders)
        report['reference_collection'] = dict(artifact=spec['artifact'], members=spec['reference_members'],
            verified=True, extraction_bytes=sum(row['bytes'] for row in spec['reference_members'].values()))
        cases = synthetic_inputs(spec['synthetic'], np)
        # Keep only the active pair of sessions alive. Every session is warmed once.
        for arm in ('unmodified', 'adapted'):
            path = references[arm+'.onnx']
            row = dict(model=spec['reference_members'][arm+'.onnx'], synthetic={}, backends={})
            pair = {}
            for mode, enum in [('disabled', ort.GraphOptimizationLevel.ORT_DISABLE_ALL),
                               ('all', ort.GraphOptimizationLevel.ORT_ENABLE_ALL)]:
                backend = StreamingBackend(path, disable_optimizations=mode == 'disabled')
                if backend.session.get_session_options().graph_optimization_level != enum:
                    raise ValueError('Actual ORT optimization level differs')
                row['backends'][mode] = backend.metadata
                pair[mode] = backend
            for name, signal in cases.items():
                values = {}
                for mode, backend in pair.items():
                    note, onset = backend.predict(signal.reshape(-1))
                    values[mode] = dict(note=note[None, ...], onset=onset[None, ...])
                row['synthetic'][name] = compare_outputs(values['disabled'], values['all'], spec['max_absolute'])
            row['synthetic_parity_pass'] = all(case['parity_pass'] for case in row['synthetic'].values())
            report['models'][arm] = row
            del pair, backend
            save_json(report_path, report)
        synthetic_pass = all(row['synthetic_parity_pass'] for row in report['models'].values())
        if not synthetic_pass:
            report['state'] = 'synthetic_parity_failed'
            report['screen'] = dict(runtime_change_screen_pass=False,
                reason='Synthetic optimization parity failed; recordings skipped', promotion_accepted=False)
            return report
        report['input_archive'] = fetch_release(spec['worker_repository'], spec['input_release'],
                                                folders['cache'], folders['inputs'], folders['logs'])
        for name, config in spec['datasets'].items():
            for suffix, key in (('.wav', 'wav_sha256'), ('.tsv', 'labels_sha256')):
                check_hash(folders['inputs']/'corpus'/(name+suffix), config[key])
            labels = read_labels(folders['inputs']/'corpus'/(name+'.tsv'))
            current = score(baseline['datasets'][name]['pitch_spans'], labels,
                            sample_count=config['sample_count'], sample_rate=config['sample_rate'])
            require_identity(current, baseline['datasets'][name]['measurement'], name+' CURRENT')
            dataset = dict(weights={})
            report['datasets'][name] = dataset
            for arm in ('unmodified', 'adapted'):
                row = {}
                dataset['weights'][arm] = row
                # Order is frozen, not chosen from observed performance.
                for mode in spec['graph_modes']:
                    report['stage'] = name+'_'+arm+'_'+mode
                    save_json(report_path, report)
                    backend = StreamingBackend(references[arm+'.onnx'], disable_optimizations=mode == 'disabled')
                    destination = folders['bulk']/(arm+'_'+mode)
                    destination.mkdir(exist_ok=True)
                    row[mode] = measure(name, config, baseline['datasets'][name], current,
                        folders['inputs'], destination, backend)
                    row[mode].pop('comparison_to_offline')
                    row[mode]['zero_compute_diagnostic'].pop('comparison_to_offline')
                    row[mode]['runtime_gates'] = runtime_gates(row[mode]['timing'])
                    del backend
                    save_json(report_path, report)
                old = folders['reference']/(arm+'_onnx')
                tf = folders['reference']/(arm+'_tensorflow')
                disabled, optimized = (folders['bulk']/(arm+'_'+mode) for mode in spec['graph_modes'])
                def parity(before, after):
                    return compare_tapes(before/(name+'-stream.npz'), after/(name+'-stream.npz'),
                        before/(name+'-events.json'), after/(name+'-events.json'), spec['max_absolute'])
                row['disabled_reference_parity'] = parity(old, disabled)
                row['optimized_vs_disabled'] = parity(disabled, optimized)
                row['optimized_vs_corrected_tensorflow'] = parity(tf, optimized)
                row['source_availability_scores_identical'] = (
                    row['disabled']['zero_compute_diagnostic']['measurement']
                    == row['all']['zero_compute_diagnostic']['measurement'])
                row['measured_clock_comparison'] = compare(row['disabled']['measurement'], row['all']['measurement'])
                row['service_p99_ratio_all_over_disabled'] = (
                    row['all']['timing']['inference_block_service_ns']['p99']
                    / row['disabled']['timing']['inference_block_service_ns']['p99'])
                save_json(report_path, report)
        report['screen'] = assess(report['datasets'], synthetic_pass)
        report['state'] = 'complete'
        return report
    except Exception as error:
        report['state'] = 'failed'
        report['error'] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        report['final'] = True
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report['elapsed_seconds'] = time.perf_counter()-start
        report['peak_resident_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        save_json(report_path, report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run(args.spec, args.output)
    print(json.dumps(dict(state=result['state'], screen=result.get('screen'))))
