"""One constant-power correction and paired TF/ORT causal comparison; GitHub CPU only."""
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

from tools.basic_pitch_flat_normalization import corrected_model, CORRECTION, CorrectedBackend
from tools.basic_pitch_onnx_export import (checked_weights, compare_outputs,
    compare_streams, export_model, variable_manifest, weight_fingerprint)
from tools.basic_pitch_streaming import SETTINGS, emission_spans
from tools.pitch_detector_comparison import compare, digest, read_labels, score
from tools.portable_basic_pitch_adaptation import assign
from tools.portable_basic_pitch_cached_diagnosis import require_identity
from tools.portable_basic_pitch_comparison import check_hash, remote_only, save_json
from tools.portable_basic_pitch_onnx_export import collect_reference
from tools.portable_basic_pitch_streaming import measure, StreamingBackend
from tools.portable_basic_pitch_trainability import download_files, synthetic_inputs
from tools.portable_direct_spectrum_learning import fetch_release


def compare_tapes(before, after, before_events, after_events, tolerance):
    with np.load(before, allow_pickle=False) as a, np.load(after, allow_pickle=False) as b:
        return compare_streams(a, b, json.loads(before_events.read_text()),
                               json.loads(after_events.read_text()), tolerance)


def run(spec_path, output):
    remote_only()
    spec = json.loads(spec_path.read_text())
    if (spec['streaming'] != SETTINGS or spec['normalization'] != CORRECTION
            or spec['ort_optimizations'] != 'disabled' or spec['max_absolute'] != 1e-4):
        raise ValueError('Frozen streaming settings differ')
    source = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True,
                            text=True, check=True).stdout.strip()
    if source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
        raise ValueError('Dispatch/source mismatch')
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache', 'inputs', 'reference', 'bulk')}
    for path in folders.values():
        path.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_basic_pitch_flat_normalization_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), source_commit=source,
        worker_commit=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
        run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], specification=spec,
        specification_sha256=digest(spec_path), installed_output_changed=False,
        promotion_accepted=False, live_readiness='not measured', exports={}, datasets={})
    save_json(report_path, report)
    start = time.perf_counter()
    try:
        import tensorflow as tf
        import tf2onnx
        import onnx
        import onnxruntime as ort
        tf.config.set_visible_devices([], 'GPU')
        tf.config.threading.set_intra_op_parallelism_threads(1)
        tf.config.threading.set_inter_op_parallelism_threads(1)
        tf.config.experimental.enable_op_determinism()
        tf.random.set_seed(spec['synthetic']['seed'])
        report['environment'] = dict(python=sys.version, platform=platform.platform(), numpy=np.__version__,
            tensorflow=tf.__version__, tf2onnx=tf2onnx.__version__, onnx=onnx.__version__,
            onnxruntime=ort.__version__, tensorflow_threads=1, onnxruntime_threads=2)
        root = Path(__file__).resolve().parents[1]
        baseline_pin = spec['baseline']
        check_hash(root/baseline_pin['path'], baseline_pin['sha256'])
        baseline = json.loads((root/baseline_pin['path']).read_text())
        references = collect_reference(spec, folders)
        report['reference_collection'] = dict(artifact=spec['artifact'], members=spec['reference_members'],
            verified=True, extraction_bytes=sum(row['bytes'] for row in spec['reference_members'].values()))
        report['public_model'] = download_files(spec['model'], folders['cache']/'public-model')
        model = tf.saved_model.load(str(folders['cache']/'public-model'/spec['model']['tensorflow_path']))
        variables = list(model.variables)
        manifest = variable_manifest(variables)
        original = [v.numpy().copy() for v in variables]
        with np.load(references['epoch-2.npz'], allow_pickle=False) as arrays:
            adapted = checked_weights(manifest, spec['variable_names'], arrays)
        report['variable_manifest'] = manifest
        report['changed_variables'] = [row['name'] for row, a, b in zip(manifest, original, adapted)
                                       if not np.array_equal(a, b)]
        if not report['changed_variables']:
            raise ValueError('Adapted checkpoint contains no changed model variable')
        cases = synthetic_inputs(spec['synthetic'], np)
        backends = {}
        for arm, weights in [('unmodified', original), ('adapted', adapted)]:
            assign(variables, weights)
            report['stage'] = 'export_'+arm
            save_json(report_path, report)
            fingerprint = weight_fingerprint(manifest, weights)
            if fingerprint != spec['weight_fingerprints'][arm]:
                raise ValueError('Weight fingerprint mismatch: '+arm)
            corrected, correction = corrected_model(model)
            path = folders['bulk']/(arm+'.onnx')
            row = dict(weight_fingerprint=fingerprint, correction=correction,
                       model=export_model(corrected, path, spec['opset'],
                           folders['report']/(arm+'-export-signature.json')),
                       synthetic={}, arithmetic_change_synthetic={})
            backend = StreamingBackend(path, disable_optimizations=True)
            row['backend'] = backend.metadata
            for name, signal in cases.items():
                input_tensor = tf.convert_to_tensor(signal)
                tensor = corrected(input_tensor)
                reference = {key: tensor[key].numpy() for key in ('note', 'onset')}
                original_tensor = model(input_tensor)
                original_outputs = {key: original_tensor[key].numpy() for key in ('note', 'onset')}
                row['arithmetic_change_synthetic'][name] = compare_outputs(
                    original_outputs, reference, spec['max_absolute'])
                note, onset = backend.predict(signal.reshape(-1))
                converted = dict(note=note[None, ...], onset=onset[None, ...])
                row['synthetic'][name] = compare_outputs(reference, converted, spec['max_absolute'])
            row['synthetic_parity_pass'] = all(case['parity_pass'] for case in row['synthetic'].values())
            report['exports'][arm] = row
            save_json(report_path, report)
            # corrected_model holds frozen constants, so later assign/restore cannot alter it.
            backends[arm] = {'tensorflow': CorrectedBackend(corrected, tf), 'onnx': backend}
            save_json(report_path, report)
        assign(variables, original)
        report['original_weights_restored'] = all(np.array_equal(v.numpy(), a) for v, a in zip(variables, original))
        if not all(row['synthetic_parity_pass'] for row in report['exports'].values()):
            report['state'] = 'conversion_parity_failed'
            report['screen'] = dict(accepted=False, reason='Synthetic backend parity failed; no corpus inference')
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
            dataset = dict(arms={})
            report['datasets'][name] = dataset
            for arm in ('unmodified', 'adapted'):
                paired = {}
                for kind in ('tensorflow', 'onnx'):
                    report['stage'] = name+'_'+arm+'_'+kind
                    save_json(report_path, report)
                    destination = folders['bulk']/(arm+'_'+kind)
                    destination.mkdir(exist_ok=True)
                    row = measure(name, config, baseline['datasets'][name], current,
                                  folders['inputs'], destination, backends[arm][kind])
                    row.pop('comparison_to_offline')
                    row['zero_compute_diagnostic'].pop('comparison_to_offline')
                    paired[kind] = row
                    dataset['arms'][arm+'_'+kind] = row
                    save_json(report_path, report)
                ref_prefix = arm+'_tensorflow/'
                old_tape = references[ref_prefix+name+'-stream.npz']
                old_events = references[ref_prefix+name+'-events.json']
                tf_dir, ort_dir = (folders['bulk']/(arm+'_'+kind) for kind in ('tensorflow', 'onnx'))
                paired['onnx']['corrected_tensorflow_readout_parity'] = compare_tapes(
                    tf_dir/(name+'-stream.npz'), ort_dir/(name+'-stream.npz'),
                    tf_dir/(name+'-events.json'), ort_dir/(name+'-events.json'), spec['max_absolute'])
                old_spans, old_audit = emission_spans(json.loads(old_events.read_text())['events'],
                                                     'available_ns', config['sample_count'])
                old_score = score(old_spans, labels, sample_count=config['sample_count'],
                                  sample_rate=config['sample_rate'])
                paired['tensorflow']['arithmetic_change_diagnostic'] = dict(
                    old_to_corrected_readout=compare_tapes(old_tape, tf_dir/(name+'-stream.npz'),
                        old_events, tf_dir/(name+'-events.json'), spec['max_absolute']),
                    old_source_available_measurement=old_score, old_event_audit=old_audit,
                    source_available_comparison=compare(old_score,
                        paired['tensorflow']['zero_compute_diagnostic']['measurement']),
                    interpretation='Changed normalization vs prior callable TensorFlow, same weights. Source-availability clock only; not a backend parity gate or compute speed claim.')
                save_json(report_path, report)
            arms = dataset['arms']
            dataset['adaptation_primary'] = compare(arms['unmodified_onnx']['measurement'],
                                                    arms['adapted_onnx']['measurement'])
            dataset['adaptation_zero_compute_diagnostic'] = compare(
                arms['unmodified_onnx']['zero_compute_diagnostic']['measurement'],
                arms['adapted_onnx']['zero_compute_diagnostic']['measurement'])
        all_parity = all(dataset['arms'][arm+'_onnx']['corrected_tensorflow_readout_parity']['parity_pass']
            for dataset in report['datasets'].values() for arm in ('unmodified', 'adapted'))
        runtime = {name: {arm: dict(
            service_p99_under_20ms=dataset['arms'][arm+'_onnx']['timing']['inference_block_service_ns']['p99'] <= 20_000_000,
            queue_max_under_26_667ms=dataset['arms'][arm+'_onnx']['timing']['queued_before_service_ns']['maximum'] <= 26_666_667)
            for arm in ('unmodified', 'adapted')} for name, dataset in report['datasets'].items()}
        quality = all(dataset['arms']['adapted_onnx']['comparison_to_current']['no_pitch_safety_regression']
            and dataset['adaptation_primary']['no_pitch_safety_regression'] for dataset in report['datasets'].values())
        gain = report['datasets']['ordinary']['arms']['adapted_onnx']['comparison_to_current']['pitch_coverage_gain_pp']
        report['screen'] = dict(corrected_backend_readout_parity_pass=all_parity, cpu_feasibility=runtime,
            strict_pitch_quality_pass=quality and gain >= 5, ordinary_gain_pp=gain,
            corrected_export_and_continuous_screen_pass=all_parity and quality and gain >= 5 and all(
                all(row.values()) for dataset in runtime.values() for row in dataset.values()),
            prior_adaptation_representation_gates_pass=False, accepted=False,
            promotion_accepted=False, installed_output_changed=False,
            interpretation='Exact constant-power correction is a new arithmetic reference. Existing weights/decoder unchanged. Prior adaptation failures remain. CPU worker feasibility does not establish native, string, host or device acceptance.')
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
