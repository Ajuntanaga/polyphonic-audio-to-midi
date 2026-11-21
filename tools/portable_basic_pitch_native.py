"""One fixed native CPU worker measurement. Recorded execution is GitHub-only."""
import argparse
import csv
from datetime import datetime, timezone
import gzip
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess

from tools.basic_pitch_cached_diagnosis import compact_measurement, decode_cached
from tools.basic_pitch_onset_decoder import clock_events
from tools.basic_pitch_streaming import CausalResampler, SETTINGS, emission_spans, ceil_div, NS
from tools.pitch_detector_comparison import compare, digest, read_labels, score
from tools.portable_basic_pitch_cached_diagnosis import cached_arrays, fetch_artifact, require_identity
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json


NATIVE = dict(input_queue_capacity=16, output_queue_capacity=16,
    callback_p99_limit_ns=166666, callback_max_limit_ns=333333,
    worker_p99_limit_ns=20000000, backlog_max_limit_ns=26666667,
    activation_absolute_tolerance=0.00001, resampler_absolute_tolerance=0.0000001,
    sdk_version='1.20.1', paced_callback=True, pitch_states=88)


def distribution(values):
    values = sorted(int(v) for v in values)
    if not values or values[0] < 0:
        raise ValueError('Expected nonempty nonnegative timing measurements')
    return dict(count=len(values), minimum=values[0], maximum=values[-1],
        p50=values[math.ceil(len(values)*.5)-1], p99=values[math.ceil(len(values)*.99)-1])


def table(path, columns):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        if reader.fieldnames != columns:
            raise ValueError('Native table schema mismatch: '+path.name)
        rows = [{k:int(v) for k,v in row.items()} for row in reader]
    if any(v < 0 for row in rows for v in row.values()):
        raise ValueError('Negative native clock/count: '+path.name)
    return rows


def sequence(rows):
    if any(r['on'] not in (0,1) or not 21 <= r['note'] <= 108 for r in rows):
        raise ValueError('Invalid native MIDI event')
    return [dict(frame=r['frame'], note=r['note'], kind='on' if r['on'] else 'off') for r in rows]


def delivered_events(rows):
    """Retain actual callback timestamps, including distinct explicit cleanup."""
    result = []
    previous = 0
    for row, event in zip(rows, sequence(rows)):
        if row['emitted_ns'] < row['ready_ns'] or row['emitted_ns'] < previous:
            raise ValueError('Backdated or unordered native delivery')
        result.append(dict(event, emitted_ns=row['emitted_ns'],
            available_ns=ceil_div(row['source_end']*NS, SETTINGS['source_rate'])))
        previous = row['emitted_ns']
    return result


def timing_report(callbacks, workers):
    durations = [r['duration_ns'] for r in callbacks]
    called = [r for r in workers if r['called']]
    summary = dict(callback_processing_ns=distribution(durations),
        callback_scheduling_lateness_ns=distribution(r['late_ns'] for r in callbacks),
        inference_block_service_ns=distribution(r['service_ns'] for r in called),
        queued_before_service_ns=distribution(r['queued_ns'] for r in workers),
        model_ns=distribution(r['model_ns'] for r in called),
        callback_allocations=sum(r['allocations'] for r in callbacks),
        callback_deallocations=sum(r['frees'] for r in callbacks),
        callback_processing_overruns=sum(v > NATIVE['callback_max_limit_ns'] for v in durations),
        callbacks_over_audio_period=sum(v > ceil_div(640*NS,96000) for v in durations))
    summary['gates'] = dict(
        callback_p99=summary['callback_processing_ns']['p99'] <= NATIVE['callback_p99_limit_ns'],
        callback_max=summary['callback_processing_ns']['maximum'] <= NATIVE['callback_max_limit_ns'],
        callback_zero_allocations=summary['callback_allocations']==0,
        callback_zero_deallocations=summary['callback_deallocations']==0,
        callback_zero_overruns=summary['callback_processing_overruns']==0,
        worker_service_p99=summary['inference_block_service_ns']['p99'] <= NATIVE['worker_p99_limit_ns'],
        worker_maximum_backlog=summary['queued_before_service_ns']['maximum'] <= NATIVE['backlog_max_limit_ns'])
    return summary


def array_comparison(actual, expected, tolerance):
    import numpy as np
    if actual.shape != expected.shape:
        return dict(pass_=False, shape_equal=False, actual_shape=list(actual.shape),
                    expected_shape=list(expected.shape))
    finite = bool(np.isfinite(actual).all() and np.isfinite(expected).all())
    error = float(np.max(np.abs(actual.astype('float64')-expected.astype('float64')))) if finite and actual.size else None
    return dict(pass_=finite and error is not None and error <= tolerance,
        shape_equal=True, bit_identical=bool(np.array_equal(actual,expected)),
        maximum_absolute_error=error, tolerance=tolerance, finite=finite)


def retain(folder, bulk, name):
    """Keep only generated model/timing/event evidence, never source audio."""
    inventory = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            raise ValueError('Unexpected native evidence directory')
        target = bulk/(name+'-'+path.name+'.gz')
        with path.open('rb') as source, gzip.open(target,'wb') as output:
            shutil.copyfileobj(source,output)
        inventory[target.name] = dict(bytes=target.stat().st_size, sha256=digest(target),
                                     uncompressed_bytes=path.stat().st_size)
    return inventory


def measure(name, config, references, inputs, cache, model, harness, scratch, logs, bulk):
    remote_only()
    import numpy as np
    import soundfile as sf
    work = scratch/name
    work.mkdir()
    mono, rate = sf.read(str(inputs/'corpus'/(name+'.wav')), dtype='float32', always_2d=True)
    mono = mono.mean(axis=1, dtype=np.float32)
    if rate != config['sample_rate'] or len(mono) != config['sample_count'] or not np.isfinite(mono).all():
        raise ValueError('Source clock or finite sample mismatch')
    resampler = CausalResampler()
    mono.astype('<f4').tofile(work/'mono.f32')
    resampler.h.astype('<f8').tofile(work/'coefficients.f64')
    result_dir = work/'native'
    # Exactly one native invocation per recording; capture before parsing.
    with (logs/(name+'.stdout')).open('wb') as stdout, (logs/(name+'.stderr')).open('wb') as stderr:
        process = subprocess.run([str(harness),str(work/'mono.f32'),str(work/'coefficients.f64'),
                                  str(model),str(result_dir)], stdout=stdout, stderr=stderr, check=False)
    if not (result_dir/'summary.json').is_file():
        raise RuntimeError(f'{name}: native exit {process.returncode}; no summary, see captured logs')
    summary = json.loads((result_dir/'summary.json').read_text())
    row = dict(native_exit=process.returncode, native=summary, bulk=retain(result_dir,bulk,name))
    if process.returncode or summary['fatal']:
        row.update(feasibility_pass=False, state='native_execution_failed')
        return row
    cached = cached_arrays(cache/(name+'-stream.npz'), stream=True)
    saved = json.loads((cache/(name+'-events.json')).read_text())
    baseline = references['baseline']['datasets'][name]
    reference = references['stream']['datasets'][name]
    original_events, original_open = decode_cached(cached['note'],cached['onset'])
    require_identity(clock_events(original_events,cached['frames'],cached['timing']),
                     saved['events'], name+' cached event clock')
    require_identity(original_open,saved['cleanup']['notes'],name+' cached cleanup')
    frames = table(result_dir/'frames.tsv', ['frame','nominal_model_sample','window_end','source_end'])
    frame_array = np.asarray([list(r.values()) for r in frames],dtype='int64')
    notes = np.fromfile(result_dir/'notes.f32',dtype='<f4').reshape(-1,88)
    onsets = np.fromfile(result_dir/'onsets.f32',dtype='<f4').reshape(-1,88)
    converted = np.fromfile(result_dir/'resampled.f32',dtype='<f4')
    python_resampled = np.concatenate([resampler.consume(mono[i:i+640]) for i in range(0,len(mono),640)])
    generated = table(result_dir/'generated.tsv', ['frame','note','on','source_end','ready_ns','emitted_ns','cleanup'])
    delivered = table(result_dir/'delivered.tsv', ['frame','note','on','source_end','ready_ns','emitted_ns','cleanup'])
    workers = table(result_dir/'worker.tsv', ['source_end','arrival_ns','started_ns','service_ns','finish_ns','queued_ns','model_ns','called'])
    callbacks = table(result_dir/'callbacks.tsv', ['source_end','started_ns','duration_ns','late_ns','allocations','frees','quiet'])
    native_events, native_open = decode_cached(notes,onsets)
    cleanup = [r for r in delivered if r['cleanup']]
    normal = [r for r in delivered if not r['cleanup']]
    row['numerical_parity'] = dict(resampling=array_comparison(converted,python_resampled,NATIVE['resampler_absolute_tolerance']),
        notes=array_comparison(notes,cached['note'],NATIVE['activation_absolute_tolerance']),
        onsets=array_comparison(onsets,cached['onset'],NATIVE['activation_absolute_tolerance']))
    row['identity_gates'] = dict(
        source_consumed=summary['consumed_samples']==len(mono),
        frame_map=bool(np.array_equal(frame_array,cached['frames'])),
        original_event_sequence=sequence(generated)==original_events,
        cpp_python_decoder=sequence(generated)==native_events,
        generated_delivered_sequence=sequence(generated)==sequence(normal),
        original_open_state=summary['open_decoder_pitches']==original_open==native_open,
        eof_cleanup=sorted(r['note'] for r in cleanup)==native_open and all(r['on']==0 for r in cleanup),
        sink_empty=summary['sink_active_after_cleanup']==0,
        dry_identity=summary['dry_identical'],
        no_queue_or_delivery_faults=all(summary[k]==0 for k in ('input_drops','output_drops','delivery_faults')))
    for event in generated:
        if event['frame'] >= len(frames) or event['source_end'] != frames[event['frame']]['source_end']:
            raise ValueError('Generated event/source clock mismatch')
    for item in workers:
        if (item['started_ns'] < item['arrival_ns'] or item['finish_ns']-item['started_ns'] != item['service_ns']
                or item['queued_ns'] != item['started_ns']-item['arrival_ns']):
            raise ValueError('Native worker clock does not reconcile')
    row['timing'] = timing_report(callbacks,workers)
    row['feasibility_pass'] = (all(row['identity_gates'].values())
        and all(r['pass_'] for r in row['numerical_parity'].values()) and all(row['timing']['gates'].values()))
    # Annotation access occurs only after native inference/delivery has finished.
    labels = read_labels(inputs/'corpus'/(name+'.tsv'))
    clock = dict(sample_count=len(mono),sample_rate=rate)
    require_identity(score(baseline['pitch_spans'],labels,**clock),baseline['measurement'],name+' CURRENT')
    for key, expected in (('emitted_ns',reference['measurement']),('available_ns',reference['zero_compute_measurement'])):
        spans,_ = emission_spans(saved['events'],key,len(mono))
        require_identity(score(spans,labels,**clock),expected,name+' saved reference '+key)
    native_delivery = delivered_events(delivered)
    diagnostic = [dict(e,available_ns=ceil_div(r['source_end']*NS,rate),emitted_ns=r['ready_ns'])
                  for e,r in zip(sequence(generated),generated)]
    row['views'] = {}
    for view, events, key in (('callback_delivery',native_delivery,'emitted_ns'),
                              ('worker_ready',diagnostic,'emitted_ns'),('zero_compute',diagnostic,'available_ns')):
        spans,audit = emission_spans(events,key,len(mono))
        measured = score(spans,labels,**clock)
        row['views'][view] = dict(measurement=measured,event_audit=audit,
            comparison_to_current=compare(baseline['measurement'],measured),
            comparison_to_python_causal=compare(reference['measurement'],measured),
            comparison_to_offline=compare(references['offline']['datasets'][name],measured))
    row['compact'] = {k:compact_measurement(v['measurement']) for k,v in row['views'].items()}
    row['state'] = 'measured'
    return row


def run(spec_path, inputs, model_checkout, harness, output):
    remote_only()
    output.mkdir(parents=True, exist_ok=False)
    folders = {k:output/k for k in ('report','logs','cache','scratch','bulk')}
    for folder in folders.values():
        folder.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_native_neural_worker_v1',state='running',final=False,datasets={},
        started_at=datetime.now(timezone.utc).isoformat(),installed_output_changed=False,promotion_accepted=False)
    try:
        spec = json.loads(spec_path.read_text())
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git','-C',str(root),'rev-parse','HEAD'])
        if (source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']
                or spec['streaming_settings'] != SETTINGS or spec['native_settings'] != NATIVE
                or os.environ.get('INPUT_SHA256') != spec['input_bundle_sha256']
                or set(spec['datasets']) != {'ordinary','extended-middle'}):
            raise ValueError('Dispatch or frozen configuration mismatch')
        if captured_text(['git','-C',str(model_checkout),'rev-parse','HEAD']) != spec['model']['commit']:
            raise ValueError('Model revision mismatch')
        model = model_checkout/spec['model']['path']
        check_hash(model,spec['model']['sha256'])
        check_hash(inputs/'recovery-inputs.json',spec['input_manifest_sha256'])
        references = {}
        for name,pin in spec['references'].items():
            path=root/pin['path'];check_hash(path,pin['sha256'])
            references[name]=json.loads(path.read_text())
        for name,config in spec['datasets'].items():
            for ext,key in (('wav','wav_sha256'),('tsv','labels_sha256')):
                check_hash(inputs/'corpus'/(name+'.'+ext),config[key])
        report['provenance'] = dict(source_commit=source,worker_commit=os.environ['GITHUB_SHA'],
            worker_repository=os.environ['GITHUB_REPOSITORY'],run_id=os.environ['GITHUB_RUN_ID'],
            run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],specification=spec,specification_sha256=digest(spec_path),
            native_executable_sha256=digest(harness),platform=platform.platform())
        report['provenance']['ort_sdk_archive_sha256'] = os.environ['ORT_SDK_SHA256']
        report['interpretation'] = ('Actual paced standalone C++ callback and separate ORT CPU worker. '
            'Callback processing excludes pacing sleep and evidence logging; lateness is separately reported. '
            'Thread-local allocation probes cover executable C calls and interposed C++ allocation, not all shared-library C calls. '
            'Worker allocations allowed. Worker service excludes evidence retention; actual queue wait includes its cost. '
            'Accepting offline sink, no VST3/DAW/device, string assignment, bends or hardware latency proof. '
            'Native feasibility and pitch-quality rejection are separate; all labels retained, installed output unchanged.')
        save_json(report_path,report)
        report['artifact'] = fetch_artifact(spec['worker_repository'],spec['artifact'],folders['cache']/'stream',folders['logs'])
        for name,config in spec['datasets'].items():
            report['stage']=name;save_json(report_path,report)
            report['datasets'][name] = measure(name,config,references,inputs,folders['cache']/'stream',
                model,harness,folders['scratch'],folders['logs'],folders['bulk'])
            save_json(report_path,report)
        rows = report['datasets']
        measured = all(r.get('state')=='measured' for r in rows.values())
        quality = (measured and rows['ordinary']['views']['callback_delivery']['comparison_to_current']['pitch_coverage_gain_pp']>=5
            and all(r['views']['callback_delivery']['comparison_to_current']['no_pitch_safety_regression'] for r in rows.values()))
        report.update(state='completed',final=True,stage='one native pass per recording complete',
            screen=dict(native_feasibility_pass=all(r['feasibility_pass'] for r in rows.values()),
                        strict_pitch_replacement_pass=quality,promotion_accepted=False))
    except Exception as error:
        report.update(state='failed',final=True,error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_or_updated_at']=datetime.now(timezone.utc).isoformat()
        save_json(report_path,report)
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('spec-path','inputs','model-checkout','harness','output'):
        parser.add_argument('--'+arg,type=Path,required=True)
    result=run(**vars(parser.parse_args()))
    print(json.dumps(dict(state=result['state'],screen=result.get('screen'),
        datasets={k:r.get('compact',r.get('state')) for k,r in result['datasets'].items()}),allow_nan=False))
