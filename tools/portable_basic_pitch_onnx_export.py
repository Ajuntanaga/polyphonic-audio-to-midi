"""Export two existing exact weight sets and measure the unchanged causal decoder.

GitHub CPU only. No fit, threshold selection, recording change, installation or
promotion. Full readout parity uses the completed TensorFlow job's saved tapes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import resource
import stat
import subprocess
import sys
import time
import zipfile

import numpy as np

from tools.basic_pitch_onnx_export import (checked_weights, compare_outputs,
    compare_streams, export_model, variable_manifest, weight_fingerprint)
from tools.basic_pitch_streaming import SETTINGS
from tools.pitch_detector_comparison import compare, digest, read_labels, score
from tools.portable_artifact_subset import captured_api
from tools.portable_basic_pitch_adaptation import assign
from tools.portable_basic_pitch_cached_diagnosis import require_identity
from tools.portable_basic_pitch_comparison import check_hash, remote_only, save_json
from tools.portable_basic_pitch_streaming import measure, StreamingBackend
from tools.portable_basic_pitch_trainability import download_files, synthetic_inputs
from tools.portable_direct_spectrum_learning import fetch_release


def collect_reference(spec, folders):
    pin = spec['artifact']
    repository = spec['worker_repository']
    metadata = folders['logs']/'reference-artifact.json'
    captured_api(f"repos/{repository}/actions/artifacts/{pin['id']}", metadata, 45)
    artifact = json.loads(metadata.read_bytes())
    if (artifact['id'] != pin['id'] or artifact['name'] != pin['name']
            or artifact['workflow_run']['id'] != pin['run_id']
            or artifact['workflow_run']['head_sha'] != pin['worker_commit']
            or artifact.get('digest') != 'sha256:'+pin['sha256']
            or artifact['size_in_bytes'] != pin['bytes'] or artifact['expired']):
        raise ValueError('Reference artifact provenance differs')
    archive = folders['cache']/'reference.zip'
    captured_api(f"repos/{repository}/actions/artifacts/{pin['id']}/zip", archive, 480)
    if archive.stat().st_size != pin['bytes']:
        raise ValueError('Reference artifact size differs')
    check_hash(archive, pin['sha256'])
    if sum(row['bytes'] for row in spec['reference_members'].values()) > 32*1024**2:
        raise ValueError('Reference member budget exceeded')
    paths = {}
    with zipfile.ZipFile(archive) as bundle:
        for name, expected in spec['reference_members'].items():
            relative = PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or '\\' in name:
                raise ValueError('Invalid reference member path')
            found = [item for item in bundle.infolist() if item.filename == name]
            if (len(found) != 1 or found[0].is_dir() or stat.S_ISLNK(found[0].external_attr >> 16)
                    or found[0].flag_bits & 1 or found[0].file_size != expected['bytes']):
                raise ValueError('Missing or invalid reference member: '+name)
            data = bundle.read(found[0])
            if hashlib.sha256(data).hexdigest() != expected['sha256']:
                raise ValueError('Reference member hash differs: '+name)
            path = folders['reference']/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            paths[name] = path
    return paths


def run(spec_path, output):
    remote_only()
    spec = json.loads(spec_path.read_text())
    if spec['streaming'] != SETTINGS:
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
    report = dict(schema='m3_basic_pitch_exact_onnx_export_v1', state='running', final=False,
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
            path = folders['bulk']/(arm+'.onnx')
            row = dict(weight_fingerprint=weight_fingerprint(manifest, weights),
                       model=export_model(model, path, spec['opset']), synthetic={})
            backend = StreamingBackend(path)
            row['backend'] = backend.metadata
            for name, signal in cases.items():
                tensor = model(tf.convert_to_tensor(signal))
                reference = {key: tensor[key].numpy() for key in ('note', 'onset')}
                note, onset = backend.predict(signal.reshape(-1))
                converted = dict(note=note[None, ...], onset=onset[None, ...])
                row['synthetic'][name] = compare_outputs(reference, converted, spec['max_absolute'])
            row['synthetic_parity_pass'] = all(case['parity_pass'] for case in row['synthetic'].values())
            report['exports'][arm] = row
            backends[arm] = backend
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
                report['stage'] = name+'_'+arm
                save_json(report_path, report)
                destination = folders['bulk']/arm
                destination.mkdir(exist_ok=True)
                row = measure(name, config, baseline['datasets'][name], current,
                              folders['inputs'], destination, backends[arm])
                row.pop('comparison_to_offline')
                row['zero_compute_diagnostic'].pop('comparison_to_offline')
                ref_prefix = arm+'_tensorflow/'
                with np.load(references[ref_prefix+name+'-stream.npz'], allow_pickle=False) as before, \
                     np.load(destination/(name+'-stream.npz'), allow_pickle=False) as after:
                    row['tensorflow_readout_parity'] = compare_streams(before, after,
                        json.loads(references[ref_prefix+name+'-events.json'].read_text()),
                        json.loads((destination/(name+'-events.json')).read_text()), spec['max_absolute'])
                dataset['arms'][arm] = row
                save_json(report_path, report)
            arms = dataset['arms']
            dataset['adaptation_primary'] = compare(arms['unmodified']['measurement'], arms['adapted']['measurement'])
            dataset['adaptation_zero_compute_diagnostic'] = compare(
                arms['unmodified']['zero_compute_diagnostic']['measurement'],
                arms['adapted']['zero_compute_diagnostic']['measurement'])
        all_parity = all(row['tensorflow_readout_parity']['parity_pass']
                         for dataset in report['datasets'].values() for row in dataset['arms'].values())
        runtime = {name: {arm: dict(service_p99_under_20ms=row['timing']['inference_block_service_ns']['p99'] <= 20_000_000,
            queue_max_under_26_667ms=row['timing']['queued_before_service_ns']['maximum'] <= 26_666_667)
            for arm, row in dataset['arms'].items()} for name, dataset in report['datasets'].items()}
        quality = all(dataset['arms']['adapted']['comparison_to_current']['no_pitch_safety_regression']
            and dataset['adaptation_primary']['no_pitch_safety_regression'] for dataset in report['datasets'].values())
        gain = report['datasets']['ordinary']['arms']['adapted']['comparison_to_current']['pitch_coverage_gain_pp']
        report['screen'] = dict(export_readout_parity_pass=all_parity, cpu_feasibility=runtime,
            strict_pitch_quality_pass=quality and gain >= 5, ordinary_gain_pp=gain,
            export_and_continuous_screen_pass=all_parity and quality and gain >= 5 and all(
                all(row.values()) for dataset in runtime.values() for row in dataset.values()),
            prior_adaptation_representation_gates_pass=False, accepted=False,
            promotion_accepted=False, installed_output_changed=False,
            interpretation='Backend conversion and paired distinct-pitch screen only. Previous adaptation representation failures remain; no string, native deadline or host/device acceptance.')
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
