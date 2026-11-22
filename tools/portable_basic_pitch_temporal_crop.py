"""One frozen readout-only convolution crop, paired on GitHub CPU.

No fitting or decoder/policy change. Original and cropped graphs run with ORT
optimization disabled. Previous TensorFlow differences remain separate.
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

from tools.basic_pitch_temporal_crop import crop_model, compare_readout, READOUT_OUTPUTS
from tools.portable_basic_pitch_graph_optimization import compare_tapes, runtime_gates
from tools.portable_basic_pitch_operator_profile import session
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
            or spec['graph_modes'] != ['original', 'cropped']
            or spec['crop_input_rows'] != [154,172]
            or spec['exposed_output_frames'] != [164,165]
            or spec['onnxruntime_version'] != '1.20.1'
            or set(spec['datasets']) != {'ordinary', 'extended-middle'}
            or spec['service_p99_limit_ns'] != 20_000_000
            or spec['queue_max_limit_ns'] != 26_666_667):
        raise ValueError('Frozen temporal-crop specification differs')


class ReadoutBackend:
    output_frame_start = 164

    def __init__(self, path, *, readout_start=164):
        remote_only()
        if type(readout_start) is not int or readout_start not in (164, 166):
            raise ValueError('Readout backend must start at frame164 or frame166')
        self.output_frame_start = readout_start
        import soundfile as sf
        import onnxruntime as ort
        self.np, self.sf = np, sf
        self.session = session(path)
        inputs = self.session.get_inputs()
        outputs = self.session.get_outputs()
        if (len(inputs) != 1 or inputs[0].name != 'serving_default_input_2:0'
                or inputs[0].shape != [1,43844,1]
                or {o.name for o in outputs} != set(READOUT_OUTPUTS.values())
                or any(o.shape != [1,2,88] for o in outputs)):
            raise ValueError('Cropped graph interface differs')
        started = time.perf_counter_ns()
        self.predict(np.zeros(43844, dtype=np.float32))
        self.metadata = dict(onnxruntime_version=ort.__version__, providers=['CPUExecutionProvider'],
            intra_op_threads=2, inter_op_threads=1, graph_optimizations='disabled',
            output_frame_start=readout_start, output_shape=[1,2,88],
            warmup='One all-zero window; excluded from service', warmup_ns=time.perf_counter_ns()-started)

    def predict(self, window):
        values = self.session.run(list(READOUT_OUTPUTS.values()),
            {'serving_default_input_2:0': window.reshape(1,43844,1).astype(np.float32, copy=False)})
        return values[0][0], values[1][0]


def assess(datasets, synthetic_pass):
    complete = set(datasets) == {'ordinary', 'extended-middle'} and all(
        set(d['weights']) == {'unmodified', 'adapted'} for d in datasets.values())
    pairs = [row for dataset in datasets.values() for row in dataset['weights'].values()]
    integrity = complete and all(row['original_reference_parity']['parity_pass'] for row in pairs)
    parity = complete and all(row['cropped_vs_original']['parity_pass'] for row in pairs)
    content = complete and all(row['source_availability_scores_identical'] for row in pairs)
    timing = complete and all(all(runtime_gates(row['cropped']['timing']).values()) for row in pairs)
    return dict(reference_reproduction_pass=integrity, cropped_backend_parity_pass=parity,
        source_availability_content_identical=content, cropped_cpu_feasibility_pass=timing,
        runtime_change_screen_pass=synthetic_pass and integrity and parity and content and timing,
        prior_corrected_tensorflow_numerical_gate='failed; not repaired by this ORT-only optimization',
        prior_adaptation_quality_pass=False, promotion_accepted=False, installed_output_changed=False,
        interpretation='Readout-only runtime feasibility, distinct from prior TensorFlow discrepancy and '
            'label/false-output/held-out failures. No native callback, allocation or hardware proof.')


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
    report = dict(schema='m3_basic_pitch_temporal_crop_v1', state='running', final=False,
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
        cropped_models = {}
        for arm in ('unmodified', 'adapted'):
            cropped_path = folders['bulk']/(arm+'-readout.onnx')
            transform = crop_model(references[arm+'.onnx'], cropped_path)
            cropped_models[arm] = cropped_path
            row = dict(transform=transform, model_sha256=digest(cropped_path),
                       model_bytes=cropped_path.stat().st_size, synthetic={}, backends={})
            original = StreamingBackend(references[arm+'.onnx'], disable_optimizations=True)
            cropped = ReadoutBackend(cropped_path)
            row['backends'] = dict(original=original.metadata, cropped=cropped.metadata)
            for name, signal in cases.items():
                a_note, a_onset = original.predict(signal.reshape(-1))
                b_note, b_onset = cropped.predict(signal.reshape(-1))
                row['synthetic'][name] = compare_readout(
                    dict(note=a_note[164:166], onset=a_onset[164:166]),
                    dict(note=b_note, onset=b_onset), spec['max_absolute'])
            row['synthetic_parity_pass'] = all(case['parity_pass'] for case in row['synthetic'].values())
            report['models'][arm] = row
            del original, cropped
            save_json(report_path, report)
        synthetic_pass = all(row['synthetic_parity_pass'] for row in report['models'].values())
        if not synthetic_pass:
            report['state'] = 'synthetic_parity_failed'
            report['screen'] = dict(runtime_change_screen_pass=False,
                reason='Synthetic crop parity failed; recordings skipped', promotion_accepted=False)
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
                    backend = (StreamingBackend(references[arm+'.onnx'], disable_optimizations=True)
                               if mode == 'original' else ReadoutBackend(cropped_models[arm]))
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
                original, cropped = (folders['bulk']/(arm+'_'+mode) for mode in spec['graph_modes'])
                def parity(before, after):
                    return compare_tapes(before/(name+'-stream.npz'), after/(name+'-stream.npz'),
                        before/(name+'-events.json'), after/(name+'-events.json'), spec['max_absolute'])
                row['original_reference_parity'] = parity(old, original)
                row['cropped_vs_original'] = parity(original, cropped)
                row['cropped_vs_corrected_tensorflow_report_only'] = parity(tf, cropped)
                row['source_availability_scores_identical'] = (
                    row['original']['zero_compute_diagnostic']['measurement']
                    == row['cropped']['zero_compute_diagnostic']['measurement'])
                row['measured_clock_comparison'] = compare(row['original']['measurement'], row['cropped']['measurement'])
                row['service_p99_ratio_cropped_over_original'] = (
                    row['cropped']['timing']['inference_block_service_ns']['p99']
                    / row['original']['timing']['inference_block_service_ns']['p99'])
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
