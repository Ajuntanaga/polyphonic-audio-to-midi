"""One frozen pretrained adaptation, executed only on the existing GitHub CPU route."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

import numpy as np

from tools.basic_pitch_adaptation import (SETTINGS, frame_summary, paired_source_results,
    render_window, representation_gate, resampled_length, window_plan)
from tools.basic_pitch_streaming import SETTINGS as STREAMING
from tools.direct_spectrum_learning import validate_manifest
from tools.pitch_detector_comparison import compare, digest, read_labels, score
from tools.portable_basic_pitch_cached_diagnosis import require_identity
from tools.portable_basic_pitch_comparison import check_hash, remote_only, save_json
from tools.portable_basic_pitch_streaming import measure
from tools.portable_basic_pitch_trainability import download_files
from tools.portable_direct_spectrum_learning import fetch_release, save_gzip_json, source_waves


def prepared_clips(takes, waves):
    remote_only()
    from scipy.signal import resample_poly
    clips = {}
    for take in takes:
        raw = waves[take['stem']][take['start_sample']:take['end_sample']]
        clip = resample_poly(raw, SETTINGS['resample_up'], SETTINGS['resample_down'],
                             window=('kaiser', 5.0), padtype='constant')
        if len(clip) != resampled_length(len(raw)) or not np.isfinite(clip).all():
            raise ValueError('Invalid resampled source')
        clips[take['key']] = clip
    return clips


def examples(plan, clips):
    remote_only()
    x = np.empty((len(plan), SETTINGS['input_samples'], 1), np.float32)
    y = np.empty((len(plan), SETTINGS['frames'], SETTINGS['notes']), bool)
    levels = []
    for i, row in enumerate(plan):
        signal, y[i], provenance = render_window(row, clips)
        x[i, :, 0] = signal
        levels.append(dict(example=i, sources=provenance))
    return x, y, levels


def assign(variables, values):
    if len(variables) != len(values):
        raise ValueError('Wrong number of saved model variables')
    for variable, value in zip(variables, values):
        variable.assign(value)
    if not all(np.array_equal(v.numpy(), old) for v, old in zip(variables, values)):
        raise ValueError('Model variable restoration was not exact')


def checked_outputs(model, tensor):
    output = {key: value.numpy() for key, value in model(tensor).items()}
    if set(output) != {'note', 'onset', 'contour'}:
        raise ValueError('Unexpected model outputs')
    for key, value in output.items():
        expected = (len(tensor), 172, 264 if key == 'contour' else 88)
        if value.shape != expected or not np.isfinite(value).all() or np.any((value < 0) | (value > 1)):
            raise ValueError('Invalid model probabilities: '+key)
    return output


def predict(model, x, tf, name):
    result = np.empty((len(x), 172, 88), np.float32)
    for left in range(0, len(x), SETTINGS['batch_size']):
        right = min(left+SETTINGS['batch_size'], len(x))
        result[left:right] = checked_outputs(model, tf.convert_to_tensor(x[left:right]))['note']
        if left % 512 == 0:
            print(f'{name}: predicted {left}/{len(x)} windows', flush=True)
    return result


def train(model, x, y, tf, bulk, report, report_path):
    remote_only()
    variables = list(model.trainable_variables)
    optimizer = tf.keras.optimizers.Adam(learning_rate=SETTINGS['learning_rate'],
        beta_1=SETTINGS['beta_1'], beta_2=SETTINGS['beta_2'], epsilon=SETTINGS['epsilon'])
    optimizer.build(variables)

    @tf.function(input_signature=[tf.TensorSpec([None, 43844, 1], tf.float32),
                                  tf.TensorSpec([None, 172, 88], tf.float32)])
    def step(signal, truth):
        with tf.GradientTape() as tape:
            p = tf.clip_by_value(model(signal)['note'], 1e-7, 1-1e-7)
            loss = -tf.reduce_mean(truth*tf.math.log(p)+(1-truth)*tf.math.log(1-p))
        gradients = tape.gradient(loss, variables)
        connected = [(v, tf.convert_to_tensor(g)) for v, g in zip(variables, gradients) if g is not None]
        if not connected:
            raise ValueError('No connected gradients')
        tf.debugging.assert_all_finite(loss, 'Nonfinite training loss')
        for _, gradient in connected:
            tf.debugging.assert_all_finite(gradient, 'Nonfinite gradient')
        clipped, norm = tf.clip_by_global_norm([g for _, g in connected], SETTINGS['clip_global_norm'])
        optimizer.apply_gradients([(g, v) for (v, _), g in zip(connected, clipped)])
        return loss, norm

    rng = np.random.default_rng(SETTINGS['shuffle_seed'])
    report['training'] = dict(epochs=[], optimizer='Adam', batch_size=SETTINGS['batch_size'],
        note_loss='Unweighted binary cross entropy over all 172x88 bins',
        batch_normalization='SavedModel inference graph; original statistics remain fixed',
        onset_and_contour='No synthetic onset/contour targets; shared-weight effects are measured later')
    for epoch in range(SETTINGS['epochs']):
        losses, norms, seconds = [], [], []
        order = rng.permutation(len(x))
        for left in range(0, len(x), SETTINGS['batch_size']):
            indices = order[left:left+SETTINGS['batch_size']]
            start = time.perf_counter()
            loss, norm = step(tf.convert_to_tensor(x[indices]), tf.convert_to_tensor(y[indices], tf.float32))
            losses.append(float(loss)); norms.append(float(norm))
            seconds.append(time.perf_counter()-start)
            if left % 512 == 0:
                print(f'epoch {epoch+1}: {left}/{len(x)} loss={losses[-1]:.7f}', flush=True)
        # One recoverable, atomic epoch artifact. No automatic resume or retry.
        arrays = {f'model_{i}': v.numpy() for i, v in enumerate(model.variables)}
        arrays.update({f'optimizer_{i}': v.numpy() for i, v in enumerate(optimizer.variables())})
        destination = bulk/f'epoch-{epoch+1}.npz'
        temporary = bulk/f'epoch-{epoch+1}.tmp'
        with temporary.open('wb') as stream:
            np.savez_compressed(stream, **arrays)
            stream.flush(); os.fsync(stream.fileno())
        temporary.replace(destination)
        row = dict(epoch=epoch+1, batches=len(losses), mean_note_bce=float(np.mean(losses)),
            global_gradient_norm_mean=float(np.mean(norms)),
            batch_seconds=dict(first=seconds[0], median=float(np.median(seconds)), maximum=max(seconds), total=sum(seconds)),
            checkpoint=dict(file=destination.name, sha256=digest(destination), bytes=destination.stat().st_size))
        save_gzip_json(bulk/f'epoch-{epoch+1}-state.json.gz', dict(shuffle_state=rng.bit_generator.state,
            variable_names=[v.name for v in model.variables], optimizer_names=[v.name for v in optimizer.variables()],
            loss=losses, gradient_norm=norms, batch_seconds=seconds))
        report['training']['epochs'].append(row)
        save_json(report_path, report)
        print(json.dumps(row), flush=True)


class Backend:
    def __init__(self, model, tf):
        import soundfile as sf
        self.model, self.tf, self.np, self.sf = model, tf, np, sf
        self.predict(np.zeros(43844, np.float32))

    def predict(self, signal):
        values = checked_outputs(self.model, self.tf.convert_to_tensor(signal.reshape(1, 43844, 1)))
        return values['note'][0], values['onset'][0]


def run(spec_path, output):
    remote_only()  # Before any model dependency, recorded input or network access.
    spec = json.loads(spec_path.read_text())
    if spec['settings'] != SETTINGS or spec['streaming'] != STREAMING:
        raise ValueError('Frozen implementation/specification mismatch')
    source = subprocess.run(['git', 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
        raise ValueError('Source/worker dispatch mismatch')
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache', 'inputs', 'bulk')}
    for folder in folders.values():
        folder.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_basic_pitch_adaptation_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), source_commit=source,
        worker_commit=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
        run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], specification=spec,
        specification_sha256=digest(spec_path), installed_output_changed=False, promotion_accepted=False,
        live_readiness='not measured', roles={}, datasets={})
    save_json(report_path, report)
    start = time.perf_counter()
    try:
        import tensorflow as tf
        import scipy
        tf.config.set_visible_devices([], 'GPU')
        tf.config.threading.set_intra_op_parallelism_threads(1)
        tf.config.threading.set_inter_op_parallelism_threads(1)
        tf.config.experimental.enable_op_determinism()
        tf.random.set_seed(SETTINGS['shuffle_seed'])
        report['environment'] = dict(python=sys.version, platform=platform.platform(), numpy=np.__version__,
            tensorflow=tf.__version__, scipy=scipy.__version__, actual_tensorflow_threads=1,
            streaming_decoder_settings=STREAMING, inference_threads_note='The inherited ONNX thread field is descriptive only; this TensorFlow backend uses one thread.')
        root = Path(__file__).resolve().parents[1]
        for pin in spec['references'].values():
            check_hash(root/pin['path'], pin['sha256'])
        manifest = json.loads((root/spec['references']['sources']['path']).read_text())
        baseline = json.loads((root/spec['references']['baseline']['path']).read_text())
        takes, counts = validate_manifest(manifest)
        if counts != {'train': 200, 'calibration': 200, 'test': 155}:
            raise ValueError('555-take split changed')
        report['retained_takes'] = counts
        plans = {role: window_plan(takes, role, SETTINGS[role+'_examples'], SETTINGS[role+'_seed'])
                 for role in ('train', 'calibration', 'test')}
        report['plans'] = {}
        for role, plan in plans.items():
            path = folders['bulk']/(role+'-plan.json.gz')
            save_gzip_json(path, plan)
            canonical = json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()
            report['plans'][role] = dict(examples=len(plan), canonical_sha256=hashlib.sha256(canonical).hexdigest(),
                source_uses=dict(Counter(c['source_key'] for row in plan for c in row['components'])))
        report['input_archives'] = [fetch_release(spec['worker_repository'], pin, folders['cache'],
            folders['inputs'], folders['logs']) for pin in spec['input_releases']]
        report['public_model'] = download_files(spec['model'], folders['cache']/'public-model')
        waves = source_waves(manifest, folders['inputs'])
        clips = prepared_clips(takes, waves)
        del waves
        model = tf.saved_model.load(str(folders['cache']/'public-model'/spec['model']['tensorflow_path']))
        original = [v.numpy().copy() for v in model.variables]
        report['variables'] = [dict(name=v.name, shape=list(v.shape), trainable=bool(v.trainable)) for v in model.variables]
        x, y, levels = examples(plans['train'], clips)
        save_gzip_json(folders['bulk']/'train-crop-levels.json.gz', levels)
        # First non-silent source anchor, before any update. Restore all outputs exactly.
        probe = tf.convert_to_tensor(x[1:2])
        reference = checked_outputs(model, probe)
        report['stage'] = 'two fixed training epochs'
        save_json(report_path, report)
        train(model, x, y, tf, folders['bulk'], report, report_path)
        adapted = [v.numpy().copy() for v in model.variables]
        report['changed_variables'] = sum(not np.array_equal(a, b) for a, b in zip(adapted, original))
        if not report['changed_variables']:
            raise ValueError('Training produced no weight change')
        assign(model.variables, original)
        restored = checked_outputs(model, probe)
        report['original_restore_output_identity'] = {k: np.array_equal(restored[k], reference[k]) for k in reference}
        if not all(report['original_restore_output_identity'].values()):
            raise ValueError('Unmodified TensorFlow reference changed')
        for role, plan in plans.items():
            report['stage'] = role+' paired window evaluation'
            save_json(report_path, report)
            if role != 'train':
                del x, y
                x, y, levels = examples(plan, clips)
                save_gzip_json(folders['bulk']/(role+'-crop-levels.json.gz'), levels)
            assign(model.variables, original)
            before = predict(model, x, tf, role+' reference')
            assign(model.variables, adapted)
            after = predict(model, x, tf, role+' adapted')
            original_summary, adapted_summary = frame_summary(before, y), frame_summary(after, y)
            paired = paired_source_results(plan, before, after)
            deltas = paired.pop('occurrence_deltas')
            save_gzip_json(folders['bulk']/(role+'-occurrence-deltas.json.gz'), deltas)
            np.savez_compressed(folders['bulk']/(role+'-windows.npz'), original=before, adapted=after, truth=y)
            report['roles'][role] = dict(original=original_summary, adapted=adapted_summary, paired=paired,
                representation_pass=representation_gate(adapted_summary, 99 if role == 'train' else 95))
            save_json(report_path, report)
        del x, y, clips, before, after
        # Always measure the two fixed recordings after a completed fit. Even a
        # rejected fit must expose complementarity, latency and per-label losses.
        for name, config in spec['datasets'].items():
            for ext, key in (('wav', 'wav_sha256'), ('tsv', 'labels_sha256')):
                check_hash(folders['inputs']/'corpus'/(name+'.'+ext), config[key])
            labels = read_labels(folders['inputs']/'corpus'/(name+'.tsv'))
            current = score(baseline['datasets'][name]['pitch_spans'], labels,
                            sample_count=config['sample_count'], sample_rate=config['sample_rate'])
            require_identity(current, baseline['datasets'][name]['measurement'], name+' CURRENT')
            rows = {}
            for arm, values in (('unmodified_tensorflow', original), ('adapted_tensorflow', adapted)):
                report['stage'] = name+' '+arm+' causal pass'
                save_json(report_path, report)
                assign(model.variables, values)
                destination = folders['bulk']/arm
                destination.mkdir(exist_ok=True)
                # measure()'s optional offline comparator is unused here; remove
                # that duplicate field to avoid misnaming a CURRENT reference.
                row = measure(name, config, baseline['datasets'][name], current,
                              folders['inputs'], destination, Backend(model, tf))
                row.pop('comparison_to_offline')
                row['zero_compute_diagnostic'].pop('comparison_to_offline')
                rows[arm] = row
            primary = compare(rows['unmodified_tensorflow']['measurement'], rows['adapted_tensorflow']['measurement'])
            diagnostic = compare(rows['unmodified_tensorflow']['zero_compute_diagnostic']['measurement'],
                                 rows['adapted_tensorflow']['zero_compute_diagnostic']['measurement'])
            report['datasets'][name] = dict(arms=rows, adaptation_primary=primary,
                adaptation_zero_compute_diagnostic=diagnostic, current_complete_score_identity=True)
            save_json(report_path, report)
        representation = all(r['representation_pass'] for r in report['roles'].values())
        occurrence = all(r['paired']['no_occurrence_loss'] for r in report['roles'].values())
        relative = all(r['adaptation_primary']['no_pitch_safety_regression'] for r in report['datasets'].values())
        current_safe = all(r['arms']['adapted_tensorflow']['comparison_to_current']['no_pitch_safety_regression']
                           for r in report['datasets'].values())
        gain = report['datasets']['ordinary']['arms']['adapted_tensorflow']['comparison_to_current']['pitch_coverage_gain_pp']
        report['screen'] = dict(representation_pass=representation, all_source_occurrences_preserved=occurrence,
            no_regression_against_unmodified_tensorflow=relative, no_regression_against_current=current_safe,
            ordinary_gain_pp=gain, research_screen_pass=all((representation, occurrence, relative, current_safe, gain >= 5)),
            promotion_accepted=False, native_allocation_and_deadlines='not measured', host_and_device='not measured')
        report.update(state='complete', final=True, stage='fixed fit and both paired recordings scored')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report.update(finished_or_updated_at=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=time.perf_counter()-start, peak_resident_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        save_json(report_path, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.spec, args.output)
    print(json.dumps(dict(state=result['state'], screen=result.get('screen')), allow_nan=False))
