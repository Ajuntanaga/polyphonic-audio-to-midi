"""Public-model synthetic gradient/restore probe. All model work runs on GHA."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import resource
import subprocess
import time
import urllib.request


def remote_only():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Model execution requires GitHub Actions')


def checked_blob(data, pin):
    actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if len(data) != pin['bytes'] or actual != pin['git_blob_sha1']:
        raise ValueError('Public model file does not match its pinned git blob')
    sha256 = hashlib.sha256(data).hexdigest()
    if pin.get('sha256', sha256) != sha256:
        raise ValueError('Public model SHA256 mismatch')
    return dict(bytes=len(data), git_blob_sha1=actual, sha256=sha256)


def download_files(spec, target):
    remote_only()
    rows = {}
    for name, pin in spec['files'].items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or not name.startswith('basic_pitch/saved_models/'):
            raise ValueError('Invalid pinned public-model path')
        url = f"https://raw.githubusercontent.com/spotify/basic-pitch/{spec['upstream_commit']}/{name}"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(pin['bytes'] + 1)
        rows[name] = checked_blob(data, pin)
        destination = target / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    return rows


def save_report(path, report):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def synthetic_inputs(spec, np):
    """Fixed synthetic signals, not a guitar-quality benchmark or fit set."""
    clock = np.arange(spec['input_samples'], dtype=np.float64) / spec['sample_rate']
    envelope = (1.0 - np.exp(-clock / 0.01)) * np.exp(-clock / 2.0)
    signals = {}
    for name, notes in spec['synthetic_cases'].items():
        signal = np.zeros_like(clock)
        for note in notes:
            frequency = 440.0 * 2.0 ** ((note - 69) / 12.0)
            for harmonic in range(1, 6):
                signal += np.sin(2 * np.pi * frequency * harmonic * clock) / harmonic
        if notes:
            signal *= 0.05 * envelope / len(notes)
        signals[name] = signal.astype(np.float32).reshape(1, -1, 1)
    return signals


def probe(spec, model_root, report, report_path):
    remote_only()
    import numpy as np
    import onnxruntime as ort
    import tensorflow as tf

    tf.config.set_visible_devices([], 'GPU')
    tf.config.threading.set_intra_op_parallelism_threads(1)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.experimental.enable_op_determinism()
    tf.random.set_seed(spec['seed'])
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model_root / spec['onnx_path']), options,
                                   providers=['CPUExecutionProvider'])
    if session.get_providers() != ['CPUExecutionProvider']:
        raise ValueError('Unexpected inference provider')
    started = time.perf_counter()
    model = tf.saved_model.load(str(model_root / spec['tensorflow_path']))
    report['load_seconds'] = time.perf_counter() - started
    variables = list(model.variables)
    trainable = list(model.trainable_variables)
    if not variables or not trainable:
        raise ValueError('SavedModel exposes no restorable/trainable variables')
    original = [variable.numpy().copy() for variable in variables]
    report['environment'] = dict(tensorflow=tf.__version__, onnxruntime=ort.__version__,
                                 numpy=np.__version__, providers=session.get_providers())
    report['variable_count'] = len(variables)
    report['trainable_variable_count'] = len(trainable)
    report['trainable_parameters'] = sum(int(np.prod(v.shape)) for v in trainable)
    report['variables'] = [dict(name=v.name, shape=list(v.shape), trainable=bool(v.trainable))
                           for v in variables]

    def outputs(signal):
        tensors = model(tf.convert_to_tensor(signal))
        if set(tensors) != set(spec['output_bins']):
            raise ValueError('Unexpected SavedModel output names')
        arrays = {key: value.numpy() for key, value in tensors.items()}
        for key, value in arrays.items():
            if value.shape != (1, spec['output_frames'], spec['output_bins'][key]):
                raise ValueError('Unexpected output shape: ' + key)
            if not np.isfinite(value).all() or value.min() < 0 or value.max() > 1:
                raise ValueError('Nonfinite or out-of-range model output: ' + key)
        return arrays

    signals = synthetic_inputs(spec, np)
    references = {}
    report['backend_comparison'] = {}
    for name, signal in signals.items():
        started = time.perf_counter()
        references[name] = outputs(signal)
        tf_seconds = time.perf_counter() - started
        started = time.perf_counter()
        ort_values = session.run(list(spec['onnx_outputs'].values()),
                                 {session.get_inputs()[0].name: signal})
        ort_seconds = time.perf_counter() - started
        metrics = {}
        for key, value in zip(spec['onnx_outputs'], ort_values):
            reference = references[name][key]
            if value.shape != reference.shape or not np.isfinite(value).all():
                raise ValueError('Invalid ONNX comparison output')
            difference = np.abs(reference - value)
            metrics[key] = dict(max_absolute=float(difference.max()), mean_absolute=float(difference.mean()),
                threshold_crossings={str(cut): int(np.count_nonzero((reference >= cut) != (value >= cut)))
                                     for cut in (0.3, 0.5)})
        report['backend_comparison'][name] = dict(outputs=metrics, tensorflow_seconds=tf_seconds,
                                                 onnx_seconds=ort_seconds)
    report['inference_preserved_variables'] = all(np.array_equal(v.numpy(), old)
                                                  for v, old in zip(variables, original))
    if not report['inference_preserved_variables']:
        raise ValueError('Reference inference changed SavedModel state')
    report['backend_parity_pass'] = all(output['max_absolute'] <= spec['backend_max_absolute']
        for case in report['backend_comparison'].values() for output in case['outputs'].values())
    save_report(report_path, report)

    signal = signals['five_pitch']
    labels = np.zeros((1, spec['output_frames'], spec['output_bins']['note']), np.float32)
    labels[:, :, [note - spec['first_output_note'] for note in spec['synthetic_cases']['five_pitch']]] = 1
    truth = tf.convert_to_tensor(labels)
    def loss_of(prediction):
        value = tf.clip_by_value(prediction, 1e-7, 1 - 1e-7)
        return -tf.reduce_mean(truth * tf.math.log(value) + (1 - truth) * tf.math.log(1 - value))

    # Inference-mode SavedModel keeps BN statistics fixed. This tests gradients,
    # not the suitability of these synthetic labels for guitar fine-tuning.
    try:
        started = time.perf_counter()
        with tf.GradientTape() as tape:
            loss = loss_of(model(tf.convert_to_tensor(signal))['note'])
        gradients = tape.gradient(loss, trainable)
        gradient_seconds = time.perf_counter() - started
        connected = [(v, tf.convert_to_tensor(g)) for v, g in zip(trainable, gradients) if g is not None]
        if not connected or not all(bool(tf.reduce_all(tf.math.is_finite(g))) for _, g in connected):
            raise ValueError('Missing or nonfinite connected gradients')
        norm = tf.linalg.global_norm([g for _, g in connected])
        if not np.isfinite(float(norm)) or float(norm) <= 0:
            raise ValueError('Zero or nonfinite gradient norm')
        clipped, _ = tf.clip_by_global_norm([g for _, g in connected], spec['clip_global_norm'])
        for (variable, _), gradient in zip(connected, clipped):
            variable.assign_sub(spec['learning_rate'] * gradient)
        updated = outputs(signal)
        report['gradient_probe'] = dict(loss_before=float(loss), loss_after=float(loss_of(updated['note'])),
            forward_backward_seconds=gradient_seconds, global_norm=float(norm),
            connected_variables=[v.name for v, _ in connected],
            unconnected_variables=[v.name for v, g in zip(trainable, gradients) if g is None],
            changed_variables=sum(not np.array_equal(v.numpy(), old) for v, old in zip(variables, original)),
            max_note_output_change=float(np.max(np.abs(updated['note'] - references['five_pitch']['note']))))
        report['gradient_probe_pass'] = (report['gradient_probe']['changed_variables'] > 0
                                         and report['gradient_probe']['max_note_output_change'] > 0)
    finally:
        for variable, old in zip(variables, original):
            variable.assign(old)
        report['restored_variables_exact'] = all(np.array_equal(v.numpy(), old)
                                                 for v, old in zip(variables, original))
        report['restored_outputs_exact'] = {}
        for name, signal in signals.items():
            restored = outputs(signal)
            report['restored_outputs_exact'][name] = all(np.array_equal(restored[key], references[name][key])
                                                         for key in restored)
        save_report(report_path, report)
    report['feasibility_pass'] = all((report['backend_parity_pass'], report['gradient_probe_pass'],
        report['restored_variables_exact'], all(report['restored_outputs_exact'].values())))


def run(spec_path, output):
    remote_only()
    spec = json.loads(spec_path.read_text())
    if os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
        raise ValueError('Unexpected worker repository')
    source_sha = subprocess.run(['git', 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if source_sha != os.environ.get('SOURCE_SHA'):
        raise ValueError('Source revision differs from dispatch pin')
    output.mkdir(parents=True, exist_ok=False)
    report_path = output / 'report.json'
    report = dict(schema='m3_basic_pitch_trainability_v1', final=False, state='running',
        started_at=datetime.now(timezone.utc).isoformat(), source_commit=source_sha,
        worker_commit=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
        run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], specification=spec,
        specification_sha256=hashlib.sha256(spec_path.read_bytes()).hexdigest(),
        recording_inputs_used=False, saved_modified_weights=False,
        installed_output_changed=False, tracking_quality='not measured', live_readiness='not measured')
    save_report(report_path, report)
    started = time.perf_counter()
    try:
        report['downloaded_files'] = download_files(spec, output / 'public-model')
        probe(spec, output / 'public-model', report, report_path)
        report.update(final=True, state='complete')
    except Exception as error:
        report.update(final=True, state='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=time.perf_counter() - started,
            peak_resident_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        save_report(report_path, report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.spec, args.output)
