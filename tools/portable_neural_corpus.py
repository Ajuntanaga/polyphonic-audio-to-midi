"""One fixed supplemental Neural Lab corpus screen on GitHub CPU only."""
import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import time

from tools.basic_pitch_cached_diagnosis import compact_measurement
from tools.basic_pitch_streaming import CausalResampler, SETTINGS, emission_spans, ceil_div, NS
from tools.frozen_cue_corpus_gate import read_replay
from tools.midi_lifecycle_analysis import read_events
from tools.neural_crop_model import SCHEMA as CROP_SCHEMA, PARENT_SHA256
from tools.pitch_detector_comparison import compare, digest, native_spans, read_labels, score
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.portable_basic_pitch_native import NATIVE, retain, sequence, table
from tools.portable_corpus_replay import command_for
from tools.portable_neural_lab import LAB, join_delivery, timing_report
from tools.portable_neural_ort_diagnosis import cpu_metadata
from tools.replay_corpus import DATASETS


CORPUS = tuple(name for name in DATASETS if name not in ('ordinary', 'extended-middle'))
CORPUS_LAB = dict(LAB, sample_formats=[32])
MODEL_SHA256 = '1b6f85ae2265d4ed5ceeda33163951c37f118766f6521b0cbe702baae933b87d'


def baseline_measurement(snapshot, midi, labels, config):
    """Check the complete replay clock and raw pairing before pitch-only scoring."""
    with snapshot.open(newline='') as stream:
        aggregate = next(csv.DictReader(stream, delimiter='\t'))
    values = {}
    for key in ('samples', 'sample_rate', 'transitions'):
        text = aggregate[key]
        if not text.isascii() or not text.isdigit():
            raise ValueError('Invalid baseline clock/transition count: ' + key)
        values[key] = int(text)
    clock = dict(sample_count=config['sample_count'], sample_rate=config['sample_rate'])
    if values['samples'] != clock['sample_count'] or values['sample_rate'] != clock['sample_rate']:
        raise ValueError('Baseline source clock differs from frozen input')
    events = read_events(midi, sample_count=clock['sample_count'], transition_count=values['transitions'])
    spans, audit = native_spans(events, **clock)
    measurement = score(spans, labels, **clock)
    return dict(measurement=measurement, compact=compact_measurement(measurement),
                event_audit=audit, snapshot_sha256=digest(snapshot), raw_midi_sha256=digest(midi))


def measure(name, config, inputs, model, replay, harness, folders):
    remote_only()
    import numpy as np
    import soundfile as sf

    work = folders['scratch'] / name
    work.mkdir()
    corpus = inputs / 'corpus'
    baseline_dir = work / 'current'
    baseline_dir.mkdir()
    snapshot, midi = baseline_dir/'snapshot.tsv', baseline_dir/'midi.tsv'
    command = command_for(replay, corpus, name, 'on', 512, work/'unused-timing.json',
                          spectral_lane_collision=True, midi_trace=midi)
    began = time.monotonic()
    with snapshot.open('wb') as stdout, (folders['logs']/(name+'-current.stderr')).open('wb') as stderr:
        process = subprocess.run(command, stdout=stdout, stderr=stderr, check=False, timeout=600)
    if process.returncode:
        raise RuntimeError(f'{name} baseline exit {process.returncode}; see captured logs')
    baseline_seconds = time.monotonic() - began

    mono, rate = sf.read(str(corpus/(name+'.wav')), dtype='float32', always_2d=True)
    mono = mono.mean(axis=1, dtype=np.float32)
    if rate != config['sample_rate'] or len(mono) != config['sample_count'] or not np.isfinite(mono).all():
        raise ValueError('Source clock or finite samples differ')
    mono.astype('<f4').tofile(work/'mono.f32')
    CausalResampler().h.astype('<f8').tofile(work/'coefficients.f64')
    folder = work/'32'
    tag = name+'-32'
    with (folders['logs']/(tag+'.stdout')).open('wb') as stdout, (folders['logs']/(tag+'.stderr')).open('wb') as stderr:
        process = subprocess.run([str(harness), str(work/'mono.f32'), str(work/'coefficients.f64'),
                                  str(model), str(folder), '32'], stdout=stdout, stderr=stderr,
                                 check=False, timeout=len(mono)/rate+120)
    if not (folder/'summary.json').is_file():
        raise RuntimeError(f'{tag}: exit {process.returncode}, no summary; see captured logs')

    # Both detector executions have finished before scoring reads annotations.
    labels = read_labels(corpus/(name+'.tsv'))
    baseline = baseline_measurement(snapshot, midi, labels, config)
    baseline.update(command=command, elapsed_seconds=baseline_seconds, replay=read_replay(snapshot),
                    bulk=retain(baseline_dir, folders['bulk'], name+'-current'))
    summary = json.loads((folder/'summary.json').read_text())
    row = dict(native_exit=process.returncode, component=summary,
               bulk=retain(folder, folders['bulk'], tag))
    result = dict(current=baseline, neural=row)
    if process.returncode or not summary['execution_pass']:
        row.update(state='component_execution_failed', integration_pass=False, quality_pass=False)
        return result

    generated = table(folder/'generated.tsv', ['frame','note','on','source_end','ready_ns'])
    delivered = table(folder/'delivered.tsv', ['note','on','host_sample','emitted_ns','cleanup'])
    callbacks = table(folder/'callbacks.tsv', ['source_end','samples','started_ns','duration_ns','late_ns','allocations','frees'])
    workers = table(folder/'worker.tsv', ['source_end','queued_ns','service_ns','model_ns'])
    native_sequence = sequence(generated)
    if any(r['source_end'] > len(mono) for r in generated):
        raise ValueError('Generated event refers to unavailable source samples')
    events, audit = join_delivery(generated, delivered, len(mono))
    row['identity_gates'] = dict(
        generated_delivery_and_pairing=True,
        sample_format=summary['sample_format']==32,
        all_source_samples=summary['source_samples']==summary['source_received']==summary['consumed_samples']==len(mono),
        dry_identity=summary['dry_identical'], vst3_event_contract=summary['event_contract'],
        sink_empty=summary['sink_active_after_cleanup']==0,
        finish_zero_allocations=summary['finish_allocations']==summary['finish_deallocations']==0,
        no_queue_or_delivery_faults=all(summary[k]==0 for k in ('input_drops','output_drops','delivery_faults')))
    row['timing'] = timing_report(callbacks, workers)
    row['integration_pass'] = all(row['identity_gates'].values()) and all(row['timing']['gates'].values())
    diagnostic = [dict(e, available_ns=ceil_div(r['source_end']*NS, rate), emitted_ns=r['ready_ns'])
                  for e,r in zip(native_sequence, generated)]
    row['views'] = {}
    for view, values, clock_key in (('component_delivery',events,'emitted_ns'),
                                   ('worker_ready',diagnostic,'emitted_ns'),
                                   ('zero_compute',diagnostic,'available_ns')):
        spans, event_audit = emission_spans(values, clock_key, len(mono))
        measured = score(spans, labels, sample_count=len(mono), sample_rate=rate)
        row['views'][view] = dict(measurement=measured, event_audit=event_audit,
                                 comparison_to_current=compare(baseline['measurement'], measured))
    row['compact'] = {key:compact_measurement(value['measurement']) for key,value in row['views'].items()}
    row.update(state='measured', delivery_audit=audit,
               quality_pass=row['views']['component_delivery']['comparison_to_current']['no_pitch_safety_regression'])
    return result


def screen(rows):
    complete = set(rows)==set(CORPUS)
    return dict(datasets_measured=sum(row['neural'].get('state')=='measured' for row in rows.values()),
                datasets_required=len(CORPUS),
                component_integration_pass=complete and all(row['neural']['integration_pass'] for row in rows.values()),
                supplemental_noninferiority_pass=complete and all(row['neural']['quality_pass'] for row in rows.values()),
                promotion_accepted=False)


def run(spec_path, inputs, model_checkout, replay, harness, bundle, output, cropped_model, crop_report):
    remote_only()
    output.mkdir(parents=True, exist_ok=False)
    folders = {key:output/key for key in ('report','logs','scratch','bulk')}
    for path in folders.values(): path.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_neural_lab_supplemental_corpus_v1', state='running', final=False, datasets={},
                  started_at=datetime.now(timezone.utc).isoformat(), installed_output_changed=False,
                  promotion_accepted=False)
    try:
        spec = json.loads(spec_path.read_text())
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git','-C',str(root),'rev-parse','HEAD'])
        if (spec['schema']!='m3_neural_lab_supplemental_corpus_spec_v1'
                or source!=os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY')!=spec['worker_repository']
                or spec['streaming_settings']!=SETTINGS or spec['lab_settings']!=CORPUS_LAB or spec['native_settings']!=NATIVE
                or os.environ.get('INPUT_SHA256')!=spec['input_bundle_sha256'] or tuple(spec['datasets'])!=CORPUS
                or spec['derived_model_sha256']!=MODEL_SHA256
                or any(c['sample_rate']!=LAB['rate'] for c in spec['datasets'].values())):
            raise ValueError('Dispatch or frozen configuration differs')
        if captured_text(['git','-C',str(model_checkout),'rev-parse','HEAD'])!=spec['model']['commit']:
            raise ValueError('Model revision differs')
        check_hash(model_checkout/spec['model']['path'], spec['model']['sha256'])
        exported = json.loads(crop_report.read_text())
        if (exported['schema']!=CROP_SCHEMA or exported['parent_sha256']!=PARENT_SHA256
                or exported['derived_sha256']!=MODEL_SHA256
                or not all(exported[k] is True for k in ('full_front_end_unchanged','weights_unchanged','onnx_check_pass'))):
            raise ValueError('Invalid model crop provenance')
        resources = bundle/'Contents/Resources'
        check_hash(cropped_model, MODEL_SHA256)
        check_hash(resources/'nmp.onnx', MODEL_SHA256)
        if (resources/'coefficients.f64').read_bytes()!=CausalResampler().h.astype('<f8').tobytes():
            raise ValueError('Packaged resampler differs')
        check_hash(inputs/'recovery-inputs.json', spec['input_manifest_sha256'])
        for name,sha in spec['shared_inputs'].items(): check_hash(inputs/'corpus'/name,sha)
        for name,config in spec['datasets'].items():
            for ext,key in (('wav','wav_sha256'),('tsv','labels_sha256')):
                check_hash(inputs/'corpus'/(name+'.'+ext),config[key])
        report['provenance'] = dict(source_commit=source, worker_commit=os.environ['GITHUB_SHA'],
            worker_repository=os.environ['GITHUB_REPOSITORY'], run_id=os.environ['GITHUB_RUN_ID'],
            run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], specification=spec, specification_sha256=digest(spec_path),
            harness_sha256=digest(harness), replay_sha256=digest(replay),
            ort_sdk_archive_sha256=os.environ['ORT_SDK_SHA256'], platform=platform.platform(),
            cpu_before=cpu_metadata(), crop_export=exported,
            bundle_files={str(p.relative_to(bundle)):dict(bytes=p.stat().st_size,sha256=digest(p))
                          for p in sorted(bundle.rglob('*')) if p.is_file() and not p.is_symlink()})
        report['interpretation'] = (
            'Twelve supplemental recordings, fresh M3 CURRENT@512 and the unchanged cropped neural component in float32. '
            'Primary quality uses accepted callback wall time; worker-ready/zero-compute are diagnostics. '
            'Pitch-only occupancy deduplicates same-pitch voices; no string/unison-multiplicity/MPE/bend result. '
            'Every label retained; no cross-dataset averaging. Earlier ordinary/middle replacement rejection remains. '
            'No new original/cropped activation or cross-format identity measurement here. '
            'Component host and package smoke do not establish external DAW/device acceptance. '
            'Allocation probes cover executable C calls and interposed C++ allocations, not all shared-library C calls. '
            'No installed output, policy or default change.')
        save_json(report_path,report)
        for name,config in spec['datasets'].items():
            report['stage'] = name
            save_json(report_path,report)
            report['datasets'][name] = measure(name,config,inputs,cropped_model,replay,harness,folders)
            save_json(report_path,report)
            print(json.dumps(dict(dataset=name,neural_state=report['datasets'][name]['neural']['state'],
                                  screen=screen(report['datasets'])),allow_nan=False),flush=True)
        report.update(state='completed',final=True,stage='all twelve supplemental datasets complete',
                      screen=screen(report['datasets']))
    except Exception as error:
        report.update(state='failed',final=True,error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['cpu_after'] = cpu_metadata()
        report['finished_or_updated_at'] = datetime.now(timezone.utc).isoformat()
        save_json(report_path,report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('spec-path','inputs','model-checkout','replay','harness','bundle','output','cropped-model','crop-report'):
        parser.add_argument('--'+arg,type=Path,required=True)
    result=run(**vars(parser.parse_args(argv)))
    print(json.dumps(dict(state=result['state'],screen=result.get('screen')),allow_nan=False))
    return 0 if result.get('screen',{}).get('component_integration_pass') is True else 1


if __name__=='__main__':
    raise SystemExit(main())
