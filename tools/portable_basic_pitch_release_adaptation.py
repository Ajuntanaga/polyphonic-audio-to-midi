"""One fresh release-context fit and paired causal test, on GitHub CPU only."""
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
    representation_gate, window_plan)
from tools.basic_pitch_release_adaptation import RELEASE, release_plan, render_release_window
from tools.basic_pitch_flat_normalization import CORRECTION, corrected_model, CorrectedBackend
from tools.basic_pitch_onnx_export import (checked_weights, compare_outputs, export_model,
    variable_manifest, weight_fingerprint)
from tools.basic_pitch_temporal_crop import crop_model, compare_readout
from tools.basic_pitch_streaming import SETTINGS as STREAMING
from tools.direct_spectrum_learning import validate_manifest
from tools.pitch_detector_comparison import compare, digest, read_labels, score
from tools.portable_basic_pitch_adaptation import (assign, checked_outputs, examples,
    prepared_clips, predict, train)
from tools.portable_basic_pitch_cached_diagnosis import require_identity
from tools.portable_basic_pitch_comparison import check_hash, remote_only, save_json
from tools.portable_basic_pitch_graph_optimization import compare_tapes, runtime_gates
from tools.portable_basic_pitch_onnx_export import collect_reference
from tools.portable_basic_pitch_streaming import measure, StreamingBackend
from tools.portable_basic_pitch_temporal_crop import ReadoutBackend
from tools.portable_basic_pitch_trainability import download_files, synthetic_inputs
from tools.portable_direct_spectrum_learning import fetch_release, save_gzip_json, source_waves


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_spec(spec):
    if (spec['settings'] != SETTINGS or spec['release'] != RELEASE
            or spec['streaming'] != STREAMING or spec['normalization'] != CORRECTION
            or spec['max_absolute'] != 1e-4 or spec['opset'] != 17
            or spec['onnxruntime_version'] != '1.20.1'
            or spec['ort_optimizations'] != 'disabled'
            or set(spec['datasets']) != {'ordinary', 'extended-middle'}
            or set(spec['reference_members']) != {'epoch-2.npz'}):
        raise ValueError('Frozen release-adaptation specification differs')


def release_examples(plan, clips):
    remote_only()
    x = np.empty((len(plan), 43844, 1), np.float32)
    y = np.empty((len(plan), 172, 88), bool)
    levels = []
    for i, row in enumerate(plan):
        signal, y[i], provenance = render_release_window(row, clips)
        x[i, :, 0] = signal
        levels.append(dict(example=row['example'], sources=provenance))
    return x, y, levels


def assess(roles, datasets, exports):
    complete = (set(roles) == {'train', 'calibration', 'test'}
        and set(datasets) == {'ordinary', 'extended-middle'}
        and set(exports) == {'prior', 'release'})
    representation = complete and all(r['representation_pass'] for r in roles.values())
    occurrence = complete and all(p['no_occurrence_loss'] for r in roles.values()
                                  for p in r['paired'].values())
    synthetic = complete and all(r['synthetic_parity_pass'] for r in exports.values())
    numerical = complete and all(r['backend_parity']['release']['parity_pass'] for r in datasets.values())
    relative = complete and all(r['release_vs_prior_primary']['no_pitch_safety_regression']
                               for r in datasets.values())
    current = complete and all(r['arms']['release_cropped']['comparison_to_current']['no_pitch_safety_regression']
                              for r in datasets.values())
    runtime = complete and all(all(r['arms']['release_cropped']['runtime_gates'].values()) for r in datasets.values())
    gain = datasets.get('ordinary', {}).get('arms', {}).get('release_cropped', {}).get(
        'comparison_to_current', {}).get('pitch_coverage_gain_pp')
    return dict(complete=complete, representation_pass=representation,
        all_source_occurrences_preserved_against_original_and_prior=occurrence,
        synthetic_export_and_crop_pass=synthetic, release_corrected_tf_parity_pass=numerical,
        no_regression_against_prior_fit=relative, no_regression_against_current=current,
        cropped_cpu_feasibility_pass=runtime, ordinary_gain_pp=gain,
        research_screen_pass=all((complete, representation, occurrence, synthetic, numerical,
            relative, current, runtime, gain is not None and gain >= 5)),
        promotion_accepted=False, installed_output_changed=False,
        prior_fit_quality_and_tf_ort_failures='remain recorded separately; not repaired by a new fit',
        native_allocation_and_deadlines='not measured', host_and_device='not measured')


def run(spec_path, output):
    remote_only()
    spec = json.loads(spec_path.read_text())
    validate_spec(spec)
    source = subprocess.run(['git', 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
        raise ValueError('Source/worker dispatch mismatch')
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache', 'inputs', 'reference', 'bulk')}
    for folder in folders.values():
        folder.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_basic_pitch_release_adaptation_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), source_commit=source,
        worker_commit=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
        run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], specification=spec,
        specification_sha256=digest(spec_path), installed_output_changed=False,
        promotion_accepted=False, live_readiness='not measured', roles={}, exports={}, datasets={})
    save_json(report_path, report)
    started = time.perf_counter()
    try:
        import tensorflow as tf
        import onnxruntime as ort
        tf.config.set_visible_devices([], 'GPU')
        tf.config.threading.set_intra_op_parallelism_threads(1)
        tf.config.threading.set_inter_op_parallelism_threads(1)
        tf.config.experimental.enable_op_determinism()
        tf.random.set_seed(SETTINGS['shuffle_seed'])
        if ort.__version__ != spec['onnxruntime_version']:
            raise ValueError('ORT version differs')
        report['environment'] = dict(python=sys.version, platform=platform.platform(), numpy=np.__version__,
            tensorflow=tf.__version__, onnxruntime=ort.__version__, tensorflow_threads=1, ort_threads=2)
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
        extra = release_plan(plans['train'])
        training_plan = plans['train'] + extra
        hashes = dict(original=canonical_hash(plans['train']), additional=canonical_hash(extra),
                      combined=canonical_hash(training_plan))
        if hashes != spec['training_plan_sha256']:
            raise ValueError('Frozen original/additional training plans differ')
        report['plans'] = {}
        for role, plan in {**plans, 'train_release_views': extra}.items():
            save_gzip_json(folders['bulk']/(role+'-plan.json.gz'), plan)
            report['plans'][role] = dict(examples=len(plan), canonical_sha256=canonical_hash(plan),
                source_uses=dict(Counter(c['source_key'] for row in plan for c in row['components'])))
        report['training_plan_sha256'] = hashes
        report['input_archives'] = [fetch_release(spec['worker_repository'], pin, folders['cache'],
            folders['inputs'], folders['logs']) for pin in spec['input_releases']]
        references = collect_reference(spec, folders)
        report['prior_reference_collection'] = dict(artifact=spec['artifact'],
            members=spec['reference_members'], verified=True)
        report['public_model'] = download_files(spec['model'], folders['cache']/'public-model')
        waves = source_waves(manifest, folders['inputs'])
        clips = prepared_clips(takes, waves)
        del waves
        model = tf.saved_model.load(str(folders['cache']/'public-model'/spec['model']['tensorflow_path']))
        variables = list(model.variables)
        vm = variable_manifest(variables)
        original = [v.numpy().copy() for v in variables]
        with np.load(references['epoch-2.npz'], allow_pickle=False) as arrays:
            prior = checked_weights(vm, spec['variable_names'], arrays)
        for name, weights in (('unmodified', original), ('adapted', prior)):
            if weight_fingerprint(vm, weights) != spec['weight_fingerprints'][name]:
                raise ValueError('Reference weights differ: '+name)
        report['variables'] = vm
        x, y, levels = release_examples(training_plan, clips)
        save_gzip_json(folders['bulk']/'training-crop-levels.json.gz', levels)
        probe = tf.convert_to_tensor(x[1:2])
        reference = checked_outputs(model, probe)
        report['stage'] = 'fresh two-epoch fit: original4096 plus release2048'
        save_json(report_path, report)
        train(model, x, y, tf, folders['bulk'], report, report_path)
        release = [v.numpy().copy() for v in variables]
        report['release_weight_fingerprint'] = weight_fingerprint(vm, release)
        report['changed_variables'] = sum(not np.array_equal(a, b) for a, b in zip(release, original))
        if not report['changed_variables']:
            raise ValueError('Training produced no weight change')
        assign(variables, original)
        restored = checked_outputs(model, probe)
        report['original_restore_output_identity'] = {k: np.array_equal(restored[k], reference[k]) for k in reference}
        if not all(report['original_restore_output_identity'].values()):
            raise ValueError('Original reference changed')
        # Only the original windows are evaluated. New training views never enter
        # calibration/test or silently enlarge the former evaluation denominators.
        for role, plan in plans.items():
            report['stage'] = role+' original/prior/release window evaluation'
            save_json(report_path, report)
            if role == 'train':
                eval_x, eval_y = x[:len(plan)], y[:len(plan)]
            else:
                eval_x, eval_y, levels = examples(plan, clips)
                save_gzip_json(folders['bulk']/(role+'-crop-levels.json.gz'), levels)
            predictions = {}
            for arm, weights in (('original', original), ('prior', prior), ('release', release)):
                assign(variables, weights)
                predictions[arm] = predict(model, eval_x, tf, role+' '+arm)
            row = {arm: frame_summary(values, eval_y) for arm, values in predictions.items()}
            row['paired'] = {}
            for comparator in ('original', 'prior'):
                paired = paired_source_results(plan, predictions[comparator], predictions['release'])
                save_gzip_json(folders['bulk']/(role+'-'+comparator+'-release-deltas.json.gz'),
                               paired.pop('occurrence_deltas'))
                row['paired'][comparator] = paired
            row['representation_pass'] = representation_gate(row['release'], 99 if role == 'train' else 95)
            np.savez_compressed(folders['bulk']/(role+'-windows.npz'), truth=eval_y, **predictions)
            report['roles'][role] = row
            save_json(report_path, report)
            del eval_x, eval_y, predictions
            if role == 'train':
                del x, y
        del clips
        # Fixed corrected exports; synthetic conversion failure stops corpus use.
        backends = {}
        cases = synthetic_inputs(spec['synthetic'], np)
        for arm, weights in (('prior', prior), ('release', release)):
            report['stage'] = arm+' corrected export and readout crop'
            save_json(report_path, report)
            assign(variables, weights)
            corrected, correction = corrected_model(model)
            full_path, cropped_path = (folders['bulk']/(arm+suffix) for suffix in ('.onnx', '-readout.onnx'))
            row = dict(weight_fingerprint=weight_fingerprint(vm, weights), correction=correction,
                full_model=export_model(corrected, full_path, spec['opset'], folders['report']/(arm+'-signature.json')),
                synthetic={})
            row['crop'] = crop_model(full_path, cropped_path)
            row['cropped_sha256'] = digest(cropped_path)
            full = StreamingBackend(full_path, disable_optimizations=True)
            cropped = ReadoutBackend(cropped_path)
            for name, signal in cases.items():
                tensor = corrected(tf.convert_to_tensor(signal))
                tf_values = {key: tensor[key].numpy() for key in ('note', 'onset')}
                note, onset = full.predict(signal.reshape(-1))
                c_note, c_onset = cropped.predict(signal.reshape(-1))
                row['synthetic'][name] = dict(
                    tensorflow_to_full=compare_outputs(tf_values, dict(note=note[None], onset=onset[None]), spec['max_absolute']),
                    full_to_crop=compare_readout(dict(note=note[164:166], onset=onset[164:166]),
                        dict(note=c_note, onset=c_onset), spec['max_absolute']))
            row['synthetic_parity_pass'] = all(
                c['tensorflow_to_full']['parity_pass'] and c['full_to_crop']['parity_pass']
                and all(v['bit_identical'] for v in c['full_to_crop']['outputs'].values())
                for c in row['synthetic'].values())
            report['exports'][arm] = row
            backends[arm] = dict(tensorflow=CorrectedBackend(corrected, tf), cropped=cropped)
            del full
            save_json(report_path, report)
        assign(variables, original)
        if not all(row['synthetic_parity_pass'] for row in report['exports'].values()):
            report.update(state='synthetic_parity_failed', final=True, stage='corpus skipped')
            report['screen'] = assess(report['roles'], {}, report['exports'])
            return report
        for name, config in spec['datasets'].items():
            for ext, key in (('wav', 'wav_sha256'), ('tsv', 'labels_sha256')):
                check_hash(folders['inputs']/'corpus'/(name+'.'+ext), config[key])
            labels = read_labels(folders['inputs']/'corpus'/(name+'.tsv'))
            current = score(baseline['datasets'][name]['pitch_spans'], labels,
                            sample_count=config['sample_count'], sample_rate=config['sample_rate'])
            require_identity(current, baseline['datasets'][name]['measurement'], name+' CURRENT')
            dataset = dict(arms={}, backend_parity={}, current_complete_score_identity=True)
            report['datasets'][name] = dataset
            for arm in ('prior', 'release'):
                for kind in ('tensorflow', 'cropped'):
                    report['stage'] = name+' '+arm+' '+kind+' causal pass'
                    save_json(report_path, report)
                    destination = folders['bulk']/(arm+'_'+kind)
                    destination.mkdir(exist_ok=True)
                    row = measure(name, config, baseline['datasets'][name], current,
                        folders['inputs'], destination, backends[arm][kind])
                    row.pop('comparison_to_offline')
                    row['zero_compute_diagnostic'].pop('comparison_to_offline')
                    row['runtime_gates'] = runtime_gates(row['timing'])
                    dataset['arms'][arm+'_'+kind] = row
                    save_json(report_path, report)
                a, b = (folders['bulk']/(arm+'_'+kind) for kind in ('tensorflow', 'cropped'))
                dataset['backend_parity'][arm] = compare_tapes(a/(name+'-stream.npz'), b/(name+'-stream.npz'),
                    a/(name+'-events.json'), b/(name+'-events.json'), spec['max_absolute'])
            before, after = (dataset['arms'][arm+'_cropped'] for arm in ('prior', 'release'))
            dataset['release_vs_prior_primary'] = compare(before['measurement'], after['measurement'])
            dataset['release_vs_prior_availability_diagnostic'] = compare(
                before['zero_compute_diagnostic']['measurement'], after['zero_compute_diagnostic']['measurement'])
            save_json(report_path, report)
        report['screen'] = assess(report['roles'], report['datasets'], report['exports'])
        report.update(state='complete', final=True, stage='fixed fit and both paired recordings scored')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report.update(finished_or_updated_at=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=time.perf_counter()-started, peak_resident_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        save_json(report_path, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.spec, args.output)
    print(json.dumps(dict(state=result['state'], screen=result.get('screen')), allow_nan=False))
