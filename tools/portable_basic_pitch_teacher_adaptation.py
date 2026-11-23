"""One frozen teacher-preservation fit and window screen on GitHub CPU only."""
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

from tools.basic_pitch_adaptation import SETTINGS, frame_summary, paired_source_results, representation_gate, window_plan
from tools.basic_pitch_teacher_adaptation import TEACHER, SCREEN, assess, objective_terms, occurrence_budget, probability_drift
from tools.basic_pitch_onnx_export import checked_weights, variable_manifest, weight_fingerprint
from tools.direct_spectrum_learning import validate_manifest
from tools.pitch_detector_comparison import digest
from tools.portable_basic_pitch_adaptation import assign, checked_outputs, examples, prepared_clips
from tools.portable_basic_pitch_comparison import check_hash, remote_only, save_json
from tools.portable_basic_pitch_onnx_export import collect_reference
from tools.portable_basic_pitch_trainability import download_files
from tools.portable_direct_spectrum_learning import fetch_release, save_gzip_json, source_waves


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_spec(spec):
    if (spec['schema'] != 'm3_basic_pitch_teacher_adaptation_spec_v1'
            or spec['settings'] != SETTINGS or spec['teacher'] != TEACHER or spec['screen'] != SCREEN
            or spec['training_plan_sha256'].keys() != {'train', 'calibration', 'test'}
            or set(spec['reference_members']) != {'epoch-2.npz'}
            or spec['protocol']['dispatches'] != 1 or spec['protocol']['fits'] != 1
            or spec['protocol']['continuous_replays'] != 0):
        raise ValueError('Frozen teacher-adaptation specification differs')


def predict_heads(model, x, tf, bulk, name):
    """Persist exact float32 targets outside the optimizer graph; return read-only maps."""
    remote_only()
    paths = {key: bulk/(name+'-'+key+'.npy') for key in ('note', 'onset')}
    maps = {key: np.lib.format.open_memmap(path, mode='w+', dtype=np.float32,
            shape=(len(x), 172, 88)) for key, path in paths.items()}
    for left in range(0, len(x), SETTINGS['batch_size']):
        right = min(left+SETTINGS['batch_size'], len(x))
        values = checked_outputs(model, tf.convert_to_tensor(x[left:right]))
        for key, array in maps.items():
            array[left:right] = values[key]
        if left % 512 == 0:
            print(f'{name}: predicted {left}/{len(x)} windows', flush=True)
    for array in maps.values():
        array.flush()
    del array, maps
    return {key: np.load(path, mmap_mode='r', allow_pickle=False) for key, path in paths.items()}


def training_objective(tf, truth, outputs, note_target, onset_target):
    return objective_terms(truth, outputs['note'], outputs['onset'],
        tf.stop_gradient(note_target), tf.stop_gradient(onset_target),
        clip=tf.clip_by_value, log=tf.math.log, mean=tf.reduce_mean)


def make_step(model, tf, optimizer):
    variables = list(model.trainable_variables)
    @tf.function(input_signature=[tf.TensorSpec([None, 43844, 1], tf.float32)]
        + [tf.TensorSpec([None, 172, 88], tf.float32)]*3)
    def step(signal, truth, teacher_note, teacher_onset):
        with tf.GradientTape() as tape:
            terms = training_objective(tf, truth, model(signal), teacher_note, teacher_onset)
        gradients = tape.gradient(terms['total'], variables)
        connected = [(v, tf.convert_to_tensor(g)) for v, g in zip(variables, gradients) if g is not None]
        if not connected:
            raise ValueError('No connected gradients')
        for key, value in terms.items():
            tf.debugging.assert_all_finite(value, 'Nonfinite loss '+key)
        for _, gradient in connected:
            tf.debugging.assert_all_finite(gradient, 'Nonfinite gradient')
        clipped, norm = tf.clip_by_global_norm([g for _, g in connected], SETTINGS['clip_global_norm'])
        optimizer.apply_gradients([(g, v) for (v, _), g in zip(connected, clipped)])
        return terms, norm
    return step


def train(model, x, y, targets, tf, bulk, report, report_path):
    remote_only()
    if any(a.flags.writeable for a in targets.values()):
        raise ValueError('Teacher targets must be immutable')
    optimizer = tf.keras.optimizers.Adam(learning_rate=SETTINGS['learning_rate'],
        beta_1=SETTINGS['beta_1'], beta_2=SETTINGS['beta_2'], epsilon=SETTINGS['epsilon'])
    optimizer.build(list(model.trainable_variables))
    step = make_step(model, tf, optimizer)
    rng = np.random.default_rng(SETTINGS['shuffle_seed'])
    report['training'] = dict(epochs=[], teacher=TEACHER, optimizer='Adam',
        batch_normalization='Original SavedModel inference statistics remain fixed',
        targets='Fixed original probabilities; no acoustic onset labels')
    for epoch in range(SETTINGS['epochs']):
        losses, norms, seconds = [], [], []
        order = rng.permutation(len(x))
        for left in range(0, len(x), SETTINGS['batch_size']):
            indices = order[left:left+SETTINGS['batch_size']]
            started = time.perf_counter()
            terms, norm = step(tf.convert_to_tensor(x[indices]), tf.convert_to_tensor(y[indices], tf.float32),
                tf.convert_to_tensor(targets['note'][indices]), tf.convert_to_tensor(targets['onset'][indices]))
            losses.append({k: float(v) for k, v in terms.items()})
            norms.append(float(norm)); seconds.append(time.perf_counter()-started)
            if left % 512 == 0:
                print(f'epoch {epoch+1}: {left}/{len(x)} {losses[-1]}', flush=True)
        arrays = {f'model_{i}': v.numpy() for i, v in enumerate(model.variables)}
        arrays.update({f'optimizer_{i}': v.numpy() for i, v in enumerate(optimizer.variables())})
        path, temporary = bulk/f'epoch-{epoch+1}.npz', bulk/f'epoch-{epoch+1}.tmp'
        with temporary.open('wb') as stream:
            np.savez_compressed(stream, **arrays)
            stream.flush(); os.fsync(stream.fileno())
        temporary.replace(path)
        save_gzip_json(bulk/f'epoch-{epoch+1}-state.json.gz', dict(
            shuffle_state=rng.bit_generator.state, shuffle_order=order.tolist(),
            variable_names=[v.name for v in model.variables],
            optimizer_names=[v.name for v in optimizer.variables()],
            loss=losses, gradient_norm=norms, batch_seconds=seconds))
        row = dict(epoch=epoch+1, batches=len(losses),
            mean_loss={k: float(np.mean([r[k] for r in losses])) for k in losses[0]},
            gradient_norm_mean=float(np.mean(norms)),
            batch_seconds=dict(first=seconds[0], median=float(np.median(seconds)),
                               maximum=max(seconds), total=sum(seconds)),
            checkpoint=dict(file=path.name, bytes=path.stat().st_size, sha256=digest(path)))
        report['training']['epochs'].append(row)
        save_json(report_path, report)
        print(json.dumps(row), flush=True)


def run(spec_path, output):
    remote_only()  # Before model dependencies, recorded inputs or network.
    spec = json.loads(spec_path.read_text())
    validate_spec(spec)
    source = subprocess.run(['git', 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
        raise ValueError('Dispatch/source mismatch')
    output.mkdir(parents=True, exist_ok=False)
    folders = {n: output/n for n in ('report', 'logs', 'cache', 'inputs', 'reference', 'bulk')}
    for path in folders.values():
        path.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_basic_pitch_teacher_adaptation_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), source_commit=source,
        worker_commit=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
        run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], specification=spec,
        specification_sha256=digest(spec_path), roles={}, integrity={},
        installed_output_changed=False, promotion_accepted=False, live_readiness='not measured')
    save_json(report_path, report)
    started = time.perf_counter()
    try:
        import tensorflow as tf
        import scipy
        tf.config.set_visible_devices([], 'GPU')
        tf.config.threading.set_intra_op_parallelism_threads(1)
        tf.config.threading.set_inter_op_parallelism_threads(1)
        tf.config.experimental.enable_op_determinism()
        tf.random.set_seed(SETTINGS['shuffle_seed'])
        report['environment'] = dict(python=sys.version, platform=platform.platform(), numpy=np.__version__,
                                    tensorflow=tf.__version__, scipy=scipy.__version__, tensorflow_threads=1)
        root = Path(__file__).resolve().parents[1]
        for pin in spec['references'].values():
            check_hash(root/pin['path'], pin['sha256'])
        manifest = json.loads((root/spec['references']['sources']['path']).read_text())
        takes, counts = validate_manifest(manifest)
        if counts != {'train': 200, 'calibration': 200, 'test': 155}:
            raise ValueError('555-take split differs')
        report['retained_takes'] = counts
        plans = {role: window_plan(takes, role, SETTINGS[role+'_examples'], SETTINGS[role+'_seed'])
                 for role in ('train', 'calibration', 'test')}
        if {k: canonical_hash(v) for k, v in plans.items()} != spec['training_plan_sha256']:
            raise ValueError('Original plans differ')
        report['plans'] = {}
        for role, plan in plans.items():
            save_gzip_json(folders['bulk']/(role+'-plan.json.gz'), plan)
            report['plans'][role] = dict(examples=len(plan), canonical_sha256=canonical_hash(plan),
                source_uses=dict(Counter(c['source_key'] for r in plan for c in r['components'])))
        report['integrity']['source_and_plan_pins'] = True
        report['stage'] = 'pinned inputs and prior weights'
        save_json(report_path, report)
        report['input_archives'] = [fetch_release(spec['worker_repository'], pin, folders['cache'],
            folders['inputs'], folders['logs']) for pin in spec['input_releases']]
        reference_paths = collect_reference(spec, folders)
        report['prior_reference_verified'] = True
        report['public_model'] = download_files(spec['model'], folders['cache']/'public-model')
        waves = source_waves(manifest, folders['inputs'])
        clips = prepared_clips(takes, waves)
        del waves
        model = tf.saved_model.load(str(folders['cache']/'public-model'/spec['model']['tensorflow_path']))
        variables = list(model.variables)
        vm = variable_manifest(variables)
        original = [v.numpy().copy() for v in variables]
        with np.load(reference_paths['epoch-2.npz'], allow_pickle=False) as arrays:
            prior = checked_weights(vm, spec['variable_names'], arrays)
        for name, weights in (('unmodified', original), ('adapted', prior)):
            if weight_fingerprint(vm, weights) != spec['weight_fingerprints'][name]:
                raise ValueError('Reference weight fingerprint differs: '+name)
        report['variables'] = vm
        report['integrity']['reference_weights'] = True
        x, y, levels = examples(plans['train'], clips)
        save_gzip_json(folders['bulk']/'train-crop-levels.json.gz', levels)
        probe = tf.convert_to_tensor(x[1:2])
        original_probe = checked_outputs(model, probe)
        report['stage'] = 'cache frozen original note/onset targets before updates'
        save_json(report_path, report)
        original_train = predict_heads(model, x, tf, folders['bulk'], 'train-original')
        cache_pins = {key: dict(file=Path(a.filename).name, sha256=digest(Path(a.filename)),
                              bytes=Path(a.filename).stat().st_size) for key, a in original_train.items()}
        report['teacher_cache'] = cache_pins
        report['stage'] = 'two fixed teacher-preservation epochs'
        save_json(report_path, report)
        train(model, x, y, original_train, tf, folders['bulk'], report, report_path)
        candidate = [v.numpy().copy() for v in variables]
        report['candidate_weight_fingerprint'] = weight_fingerprint(vm, candidate)
        report['changed_variables'] = [v['name'] for v, a, b in zip(vm, original, candidate)
                                       if not np.array_equal(a, b)]
        if not report['changed_variables']:
            raise ValueError('Training made no weight change')
        for key, array in original_train.items():
            check_hash(Path(array.filename), cache_pins[key]['sha256'])
        report['integrity']['teacher_cache_unchanged'] = True
        assign(variables, original)
        restored = checked_outputs(model, probe)
        report['original_restore_output_identity'] = {k: np.array_equal(v, restored[k])
                                                      for k, v in original_probe.items()}
        if not all(report['original_restore_output_identity'].values()):
            raise ValueError('Original output restoration differs')
        report['integrity']['original_output_identity'] = True
        for role, plan in plans.items():
            report['stage'] = role+' original/prior/teacher paired window screen'
            save_json(report_path, report)
            if role != 'train':
                x, y, levels = examples(plan, clips)
                save_gzip_json(folders['bulk']/(role+'-crop-levels.json.gz'), levels)
            predictions = {}
            for arm, weights in (('original', original), ('prior', prior), ('teacher', candidate)):
                assign(variables, weights)
                predictions[arm] = original_train if role == 'train' and arm == 'original' else predict_heads(
                    model, x, tf, folders['bulk'], role+'-'+arm)
            row = {arm: frame_summary(values['note'], y) for arm, values in predictions.items()}
            row['paired'], row['drift_vs_original'] = {}, {}
            for arm in ('prior', 'teacher'):
                row['drift_vs_original'][arm] = {key: probability_drift(predictions['original'][key],
                    predictions[arm][key], .3 if key == 'note' else .5) for key in ('note', 'onset')}
            for comparator in ('original', 'prior'):
                paired = paired_source_results(plan, predictions[comparator]['note'], predictions['teacher']['note'])
                deltas = paired.pop('occurrence_deltas')
                paired['budget'] = occurrence_budget(deltas)
                save_gzip_json(folders['bulk']/(role+'-'+comparator+'-teacher-deltas.json.gz'), deltas)
                row['paired'][comparator] = paired
            row['representation_pass'] = representation_gate(row['teacher'], 99 if role == 'train' else 95)
            np.save(folders['bulk']/(role+'-truth.npy'), y, allow_pickle=False)
            report['roles'][role] = row
            save_json(report_path, report)
            del x, y, predictions
        assign(variables, original)
        report['integrity']['original_weights_restored_at_end'] = all(
            np.array_equal(v.numpy(), a) for v, a in zip(variables, original))
        report['screen'] = assess(report['roles'], report['integrity'])
        report.update(state='complete', final=True, stage='fixed window screen final; no continuous replay')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report.update(finished_or_updated_at=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=time.perf_counter()-started,
            peak_resident_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        save_json(report_path, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.spec, args.output)
    print(json.dumps(dict(state=result['state'], screen=result.get('screen')), allow_nan=False))
