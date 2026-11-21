"""One frozen causal bass-register comparison, executed only on GitHub CPU."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys

from tools.basic_pitch_bass_view import BASS_VIEW, View, mapped_bass_event, stream_pair
from tools.basic_pitch_cached_diagnosis import compact_measurement
from tools.basic_pitch_streaming import SETTINGS, NS, ceil_div, emission_spans, timing_summary
from tools.neural_crop_model import export
from tools.pitch_detector_comparison import compare, digest, read_labels, score
from tools.portable_basic_pitch_cached_diagnosis import cached_arrays, fetch_artifact, require_identity
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.portable_basic_pitch_streaming import StreamingBackend

REFERENCE_CROP_SHA = '1b6f85ae2265d4ed5ceeda33163951c37f118766f6521b0cbe702baae933b87d'
FRAME_COLUMNS = ['frame','nominal_model_sample','window_end_exclusive','arrived_source_samples']
TIMING_COLUMNS = ['source_end','arrival_ns','service_ns','finish_ns','queued_ns',
                  'resample_and_buffer_ns','model_ns','decode_ns','model_called']


def stable_events(events):
    return [{k:e[k] for k in ('kind','note','frame','available_ns')} for e in events]


def activation_identity(actual, expected):
    import numpy as np
    differences = {}
    for key in ('notes','onsets'):
        a,b = np.asarray(actual[key]),np.asarray(expected[key])
        if a.shape != b.shape or not a.size or not np.isfinite(a).all() or not np.isfinite(b).all():
            raise ValueError('Activation shape/finite identity failure: '+key)
        differences[key] = float(np.max(np.abs(a-b)))
        if differences[key] > BASS_VIEW['crop_tolerance']:
            raise ValueError('Activation tolerance exceeded: '+key)
    if not np.array_equal(actual['frames'],expected['frames']):
        raise ValueError('Frame/source availability identity failed')
    require_identity(stable_events(actual['events']),stable_events(expected['events']),
                     'event sequence and source availability')
    require_identity(actual['open_decoder_pitches'],expected['open_decoder_pitches'],'EOF state')
    return dict(pass_=True,maximum_absolute_error=differences,
                frame_mapping_identical=True,event_sequence_identical=True,eof_state_identical=True)


def chunks(audio):
    while True:
        block = audio.read(640,dtype='float32',always_2d=True)
        if not len(block):
            return
        yield block


def low_pitch_coverage(spans, labels, clock):
    # Distinct low pitches, not a sum of overlapping same-pitch label durations.
    measured = score([s for s in spans if s[2]<60],
                     [r for r in labels if r['midi_note']<60],**clock)
    totals = measured['pitch_sets']['totals']
    expected,present = totals['expected_pitch_samples'],totals['present_pitch_samples']
    return dict(expected_pitch_samples=expected,present_pitch_samples=present,
                percent=100*present/expected if expected else None)


def score_events(events, labels, clock):
    views = {}
    for name,key in (('serviced','emitted_ns'),('zero_compute','available_ns')):
        spans,audit = emission_spans(events,key,clock['sample_count'])
        measurement = score(spans,labels,**clock)
        views[name] = dict(measurement=measurement,compact=compact_measurement(measurement),
                           event_audit=audit,low_pitch_coverage=low_pitch_coverage(spans,labels,clock))
    return views


def measure(name, config, current, offline, inputs, bulk, cache, reference, bass):
    remote_only()
    wav = inputs/'corpus'/(name+'.wav')
    info = reference.sf.info(str(wav))
    if info.samplerate != 96000 or info.frames != config['sample_count']:
        raise ValueError('Recording clock mismatch')
    print(name+': measured paired pass starting',flush=True)
    with reference.sf.SoundFile(str(wav)) as audio:
        result = stream_pair(chunks(audio),info.frames,reference,bass,
            progress=lambda a,b,s: print(f'{name}: 1x={a},2x={b},source={s}/{info.frames}',flush=True))
    if not result['reference']['model_calls'] or not result['bass']['model_calls']:
        raise ValueError('No model output')
    saved = cached_arrays(cache/(name+'-stream.npz'),stream=True)
    saved_events = json.loads((cache/(name+'-events.json')).read_text())
    identity = activation_identity(result['reference'],dict(notes=saved['note'],onsets=saved['onset'],
        frames=saved['frames'],events=saved_events['events'],
        open_decoder_pitches=saved_events['cleanup']['notes']))
    cleanup = max(ceil_div(info.frames*NS,96000),result['worker_finish_ns'])
    files = []
    for view in ('reference','bass'):
        row = result[view]
        path = bulk/(name+'-'+view+'.npz')
        reference.np.savez_compressed(path,note=row['notes'],onset=row['onsets'],
            frames=reference.np.asarray(row['frames'],dtype='int64'),
            timing=reference.np.asarray(result['timing'],dtype='int64'))
        files.append(path)
        path = bulk/(name+'-'+view+'-events.json')
        save_json(path,dict(events=row['events'],cleanup=dict(emitted_ns=cleanup,notes=row['open_decoder_pitches']),
                           frame_columns=FRAME_COLUMNS,timing_columns=TIMING_COLUMNS))
        files.append(path)
    path = bulk/(name+'-combined-events.json')
    save_json(path,dict(events=result['combined_events'],
        cleanup=dict(emitted_ns=cleanup,notes=result['combined_open_pitches']),
        ownership='1x at/above60;2x mapped down12 below60;all on original source clock'))
    files.append(path)
    # Annotation values are first read only after both models and decoders finish.
    labels = read_labels(inputs/'corpus'/(name+'.tsv'))
    clock = dict(sample_count=info.frames,sample_rate=96000)
    bass_events = [mapped for e in result['bass']['events'] if (mapped:=mapped_bass_event(e)) is not None]
    arms = {key:score_events(events,labels,clock) for key,events in (
        ('reference_1x',result['reference']['events']),('bass_only',bass_events),
        ('combined',result['combined_events']),('historical_stream',saved_events['events']))}
    for row in arms.values():
        for view,values in row.items():
            values['comparison_to_current'] = compare(current['measurement'],values['measurement'])
            values['comparison_to_offline'] = compare(offline,values['measurement'])
            values['comparison_to_same_pass_1x'] = compare(arms['reference_1x'][view]['measurement'],values['measurement'])
            values['comparison_to_historical_stream'] = compare(arms['historical_stream'][view]['measurement'],values['measurement'])
    measured = dict(audio=dict(**clock,channels=info.channels),arms=arms,
        reference_identity=identity,bass_crop_identity='pending untimed companion',
        timing=timing_summary(result['timing']),model_calls={v:result[v]['model_calls'] for v in ('reference','bass')},
        source_samples_consumed=result['source_samples'],worker_finish_ns=result['worker_finish_ns'],
        cleanup_emitted_ns=cleanup,
        bulk={p.name:dict(bytes=p.stat().st_size,sha256=digest(p)) for p in files})
    return measured


def original_bass_companion(name, config, inputs, bulk, original):
    remote_only()
    class Readout:
        def predict(self, window):
            note,onset = original.predict(window)
            return note[168:170],onset[168:170]
    view = View(Readout(),2)
    source_end = 0
    print(name+': untimed original168/169 identity companion',flush=True)
    with original.sf.SoundFile(str(inputs/'corpus'/(name+'.wav'))) as audio:
        for block in chunks(audio):
            source_end += len(block)
            mono = block.mean(axis=1,dtype=original.np.float32)
            batch = view.consume(mono,source_end,source_end==config['sample_count'])
            arrival = ceil_div(source_end*NS,96000)
            view.retain(batch,arrival,arrival)
    if source_end != config['sample_count'] or len(view.pending):
        raise ValueError('Incomplete companion input')
    expected = cached_arrays(bulk/(name+'-bass.npz'),stream=True)
    events = json.loads((bulk/(name+'-bass-events.json')).read_text())
    identity = activation_identity(view.result(),dict(notes=expected['note'],onsets=expected['onset'],
        frames=expected['frames'],events=events['events'],open_decoder_pitches=events['cleanup']['notes']))
    return dict(**identity,model_calls=view.calls,scope='Every2x window; untimed original model168/169')


def assess(datasets):
    ordinary = datasets['ordinary']['arms']
    before = ordinary['reference_1x']['serviced']['low_pitch_coverage']
    after = ordinary['combined']['serviced']['low_pitch_coverage']
    gain = after['percent']-before['percent']
    deltas = ordinary['combined']['serviced']['comparison_to_same_pass_1x']['label_deltas']
    recovered = [r['label_index'] for r in deltas if r['midi_note']<60
                 and r['current_present_samples']==0 and r['model_present_samples']>0]
    useful = gain >= 5 and bool(recovered)
    incremental = useful and all(d['arms']['combined']['serviced']['comparison_to_same_pass_1x']
        ['no_pitch_safety_regression'] for d in datasets.values())
    current = ordinary['combined']['serviced']['comparison_to_current']
    strict_current = current['pitch_coverage_gain_pp']>=5 and all(
        d['arms']['combined']['serviced']['comparison_to_current']['no_pitch_safety_regression']
        for d in datasets.values())
    return dict(low_pitch_coverage_gain_pp=gain,previously_zero_low_labels_recovered=recovered,
        practical_usefulness_pass=useful,incremental_noninferiority_pass=incremental,
        strict_current_replacement_pass=strict_current,
        cpu_feasibility={n:dict(service_p99_under_20ms=d['timing']['inference_block_service_ns']['p99']<=20_000_000,
            maximum_queued_backlog_under_26_667ms=d['timing']['queued_before_service_ns']['maximum']<=26_666_667)
            for n,d in datasets.items()},promotion_accepted=False,installed_output_changed=False)


def run(spec_path, inputs, model_checkout, output):
    remote_only()  # Before any source recording, output directory or model access.
    output.mkdir(parents=True,exist_ok=False)
    report_dir,bulk,logs = (output/n for n in ('report','bulk','logs'))
    for path in (report_dir,bulk,logs): path.mkdir()
    report_path = report_dir/'report.json'
    report = dict(schema='m3_basic_pitch_bass_view_v1',state='running',final=False,datasets={},
        started_at=datetime.now(timezone.utc).isoformat(),promotion_accepted=False,installed_output_changed=False)
    try:
        spec = json.loads(spec_path.read_text())
        if spec['streaming'] != SETTINGS or spec['bass_view'] != BASS_VIEW:
            raise ValueError('Implementation differs from frozen settings')
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git','-C',str(root),'rev-parse','HEAD'])
        if source!=os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY')!=spec['worker_repository']:
            raise ValueError('Dispatch pin mismatch')
        if captured_text(['git','-C',str(model_checkout),'rev-parse','HEAD'])!=spec['model']['commit']:
            raise ValueError('Model checkout pin mismatch')
        model = model_checkout/spec['model']['path']
        check_hash(model,spec['model']['sha256'])
        if os.environ.get('INPUT_SHA256')!=spec['input_bundle_sha256']:
            raise ValueError('Input release pin mismatch')
        check_hash(inputs/'recovery-inputs.json',spec['input_manifest_sha256'])
        baseline_path,offline_path = root/spec['baseline_file'],root/spec['offline_reference_file']
        check_hash(baseline_path,spec['baseline_sha256']);check_hash(offline_path,spec['offline_reference_sha256'])
        baseline,offline = json.loads(baseline_path.read_text()),json.loads(offline_path.read_text())
        if set(spec['datasets'])!={'ordinary','extended-middle'}:
            raise ValueError('Both fixed recordings required')
        for name,config in spec['datasets'].items():
            if config['sample_rate']!=96000: raise ValueError('Only original96k clock is allowed')
            for ext,key in (('wav','wav_sha256'),('tsv','labels_sha256')):
                check_hash(inputs/'corpus'/(name+'.'+ext),config[key])
            saved = baseline['datasets'][name]
            if any(saved[k]!=config['baseline'][k] for k in ('raw_midi_sha256','source_commit','run_id')) or saved['labels_sha256']!=config['labels_sha256']:
                raise ValueError('CURRENT baseline provenance mismatch')
        report['provenance'] = dict(source_commit=source,worker_commit=os.environ['GITHUB_SHA'],
            worker_repository=os.environ['GITHUB_REPOSITORY'],run_id=os.environ['GITHUB_RUN_ID'],
            run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],specification=spec,
            specification_sha256=digest(spec_path),python=sys.version,platform=platform.platform())
        report['scope'] = dict(primary='Measured serial FIFO including both views on original96k clock',
            diagnostic='Zero-compute input availability; same decoded events',
            caveat='The2x waveform view changes frequency AND temporal context; no pure frequency attribution',
            no_claims=['physical attack latency','native callback safety','host/device MIDI','strings/unison multiplicity','installed improvement'])
        (report_dir/'environment.txt').write_text(captured_text([sys.executable,'-m','pip','freeze','--all'])+'\n')
        cache = output/'reference-cache'
        report['reference_artifact'] = fetch_artifact(spec['worker_repository'],spec['stream_reference_artifact'],cache,logs)
        models = output/'models';models.mkdir()
        ref_model,bass_model = models/'readout164.onnx',models/'readout168.onnx'
        report['reference_crop'] = export(model,ref_model,report_dir/'reference-crop.json')
        check_hash(ref_model,REFERENCE_CROP_SHA)
        report['bass_crop'] = export(model,bass_model,report_dir/'bass-crop.json',readout_start=168)
        reference,bass = StreamingBackend(ref_model),StreamingBackend(bass_model)
        report['backends'] = dict(reference=reference.metadata,bass=bass.metadata)
        for name,config in spec['datasets'].items():
            report['stage'] = name+' measured paired pass';save_json(report_path,report)
            report['datasets'][name] = measure(name,config,baseline['datasets'][name],offline['datasets'][name],
                inputs,bulk,cache,reference,bass)
            save_json(report_path,report)
        # Only load/run the full original session after BOTH timed passes finish.
        del reference,bass
        original = StreamingBackend(model)
        for name,config in spec['datasets'].items():
            report['stage'] = name+' untimed identity companion';save_json(report_path,report)
            report['datasets'][name]['bass_crop_identity'] = original_bass_companion(name,config,inputs,bulk,original)
            save_json(report_path,report)
        report.update(state='completed',final=True,stage='Both recordings scored and identity companions passed',
                      screen=assess(report['datasets']))
    except Exception as error:
        report.update(state='failed',final=True,error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_or_updated_at'] = datetime.now(timezone.utc).isoformat()
        save_json(report_path,report)
    return report


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('spec','inputs','model-checkout','output'):
        parser.add_argument('--'+arg,dest='spec_path' if arg=='spec' else arg.replace('-','_'),type=Path,required=True)
    result = run(**vars(parser.parse_args()))
    print(json.dumps(dict(state=result['state'],screen=result['screen']),allow_nan=False))
