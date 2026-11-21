"""One fixed actual-component integration screen, executed only on GitHub Actions."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess

from tools.basic_pitch_cached_diagnosis import compact_measurement, decode_cached
from tools.basic_pitch_onset_decoder import clock_events
from tools.basic_pitch_streaming import CausalResampler, SETTINGS, emission_spans, ceil_div, NS
from tools.pitch_detector_comparison import compare, digest, read_labels, score
from tools.portable_basic_pitch_cached_diagnosis import cached_arrays, fetch_artifact, require_identity
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.portable_basic_pitch_native import NATIVE, distribution, retain, sequence, table
from tools.portable_neural_ort_diagnosis import cpu_metadata
from tools.neural_crop_model import SCHEMA as CROP_SCHEMA, PARENT_SHA256


LAB = dict(sample_formats=[32,64], callback_pattern=[32,512,1024], maximum_block=1024,
    rate=96000, mono_channels=1, package_stereo_test=True, pitch_states=88,
    midi_channel=1, midi_velocity=100, output_sample_offset=0,
    input_queue_capacity=16, output_queue_capacity=16,
    callback_p99_limit_ns=166666, callback_max_limit_ns=333333,
    worker_p99_limit_ns=20000000, backlog_max_limit_ns=26666667)

CROP = dict(schema=CROP_SCHEMA, retained_time_range=[144,172], original_readout=[164,165],
    full_front_end_unchanged=True, weights_unchanged=True, activation_absolute_tolerance=1e-5,
    generated_event_identity=True, paired_every_window=True)


def crop_identity(folder,cached,original,open_notes,source_samples):
    """Numerical and event gates against both same-run original and saved Python."""
    import numpy as np
    summary=json.loads((folder/'summary.json').read_text())
    values={key:np.fromfile(folder/(key+'s.f32'),dtype='<f4').reshape(-1,88) for key in ('note','onset')}
    frames=table(folder/'frames.tsv',['frame','source_end'])
    if any(values[key].shape!=cached[key].shape for key in values):
        raise ValueError('Cropped output frame count differs from saved original')
    errors={key:float(np.max(np.abs(values[key].astype(np.float64)-cached[key]))) for key in values}
    decoded,opened=decode_cached(values['note'],values['onset'])
    gates=dict(same_run_original=summary['paired_identity_pass'] is True,
        complete_source=summary['source_samples']==source_samples,
        complete_frames=summary['frames']==len(frames)==len(cached['frames']),
        source_mapping=len(frames)==len(cached['frames']) and all(
            row['frame']==i and row['source_end']==int(cached['frames'][i,3]) for i,row in enumerate(frames)),
        cached_note_error=errors['note']<=CROP['activation_absolute_tolerance'],
        cached_onset_error=errors['onset']<=CROP['activation_absolute_tolerance'],
        cached_generated_sequence=decoded==original,cached_eof_owners=opened==open_notes)
    return dict(paired=summary,cached_maximum_activation_error=errors,gates=gates,passed=all(gates.values()))


def join_delivery(generated, delivered, source_samples):
    """Associate accepted callbacks with generated events, never backdate delivery."""
    expected=sequence(generated)
    result=[];normal=[];cleanup=[];active=set();previous=0;index=0;cleaning=False
    for row in delivered:
        note,on,flag=row['note'],row['on'],row['cleanup']
        if not 21<=note<=108 or on not in (0,1) or flag not in (0,1):
            raise ValueError('Invalid delivered pitch event')
        if row['emitted_ns']<previous or row['host_sample']>source_samples:
            raise ValueError('Unordered delivery or invalid callback source position')
        if flag:
            cleaning=True
            if on or note not in active:
                raise ValueError('Cleanup does not release an accepted owner')
            event=dict(frame=0,note=note,kind='off');source_end=source_samples;cleanup.append(note)
        else:
            if cleaning or index>=len(generated):
                raise ValueError('Unexpected generated/delivered event count or cleanup order')
            gen=generated[index];event=expected[index];index+=1
            if note!=gen['note'] or on!=gen['on']:
                raise ValueError('Generated/delivered event sequence differs')
            if row['emitted_ns']<gen['ready_ns']:
                raise ValueError('Delivery precedes worker readiness')
            source_end=gen['source_end'];normal.append(event)
        available=ceil_div(source_end*NS,LAB['rate'])
        if row['emitted_ns']<available:
            raise ValueError('Delivery precedes source availability')
        if on:
            if note in active: raise ValueError('Duplicate accepted NoteOn')
            active.add(note)
        else:
            if note not in active: raise ValueError('NoteOff without accepted owner')
            active.remove(note)
        result.append(dict(event,emitted_ns=row['emitted_ns'],available_ns=available))
        previous=row['emitted_ns']
    if index!=len(generated) or active:
        raise ValueError('Lost generated event or missing explicit EOF cleanup')
    return result,dict(normal_count=len(normal),cleanup_notes=sorted(cleanup),active_after_cleanup=0)


def timing_report(callbacks,workers):
    called=[r for r in workers if r['model_ns']>0]
    if any(not 0<=r['samples']<=LAB['maximum_block'] for r in callbacks):
        raise ValueError('Callback size outside frozen bounds')
    times=[r['duration_ns'] for r in callbacks]
    row=dict(callback_processing_ns=distribution(times),
        callback_scheduling_lateness_ns=distribution(r['late_ns'] for r in callbacks),
        inference_block_service_ns=distribution(r['service_ns'] for r in called),
        model_ns=distribution(r['model_ns'] for r in called),
        queued_before_service_ns=distribution(r['queued_ns'] for r in workers),
        callback_allocations=sum(r['allocations'] for r in callbacks),
        callback_deallocations=sum(r['frees'] for r in callbacks),
        callback_processing_overruns=sum(v>LAB['callback_max_limit_ns'] for v in times),
        callbacks_over_audio_period=sum(r['samples']>0 and r['duration_ns']>ceil_div(r['samples']*NS,LAB['rate'])
                                        for r in callbacks),
        callback_sizes=sorted(set(r['samples'] for r in callbacks)))
    row['gates']=dict(
        callback_p99=row['callback_processing_ns']['p99']<=LAB['callback_p99_limit_ns'],
        callback_max=row['callback_processing_ns']['maximum']<=LAB['callback_max_limit_ns'],
        callback_zero_allocations=row['callback_allocations']==0,
        callback_zero_deallocations=row['callback_deallocations']==0,
        callback_zero_overruns=row['callback_processing_overruns']==0,
        callback_audio_period=row['callbacks_over_audio_period']==0,
        variable_callback_sizes=all(v in row['callback_sizes'] for v in LAB['callback_pattern']),
        worker_service_p99=row['inference_block_service_ns']['p99']<=LAB['worker_p99_limit_ns'],
        worker_maximum_backlog=row['queued_before_service_ns']['maximum']<=LAB['backlog_max_limit_ns'])
    return row


def measure(name,config,references,inputs,cache,model,harness,scratch,logs,bulk,crop=None):
    remote_only()
    import numpy as np
    import soundfile as sf
    work=scratch/name;work.mkdir()
    mono,rate=sf.read(str(inputs/'corpus'/(name+'.wav')),dtype='float32',always_2d=True)
    mono=mono.mean(axis=1,dtype=np.float32)
    if rate!=config['sample_rate'] or len(mono)!=config['sample_count'] or not np.isfinite(mono).all():
        raise ValueError('Source clock or finite samples differ')
    mono.astype('<f4').tofile(work/'mono.f32')
    CausalResampler().h.astype('<f8').tofile(work/'coefficients.f64')
    cached=cached_arrays(cache/(name+'-stream.npz'),stream=True)
    saved=json.loads((cache/(name+'-events.json')).read_text())
    original,open_notes=decode_cached(cached['note'],cached['onset'])
    require_identity(clock_events(original,cached['frames'],cached['timing']),saved['events'],name+' cached clock')
    require_identity(open_notes,saved['cleanup']['notes'],name+' cached EOF owners')
    baseline=references['baseline']['datasets'][name]
    reference=references['stream']['datasets'][name]
    formats={};sequences={}
    paired=None
    if crop:
        folder=work/'paired';tag=name+'-paired'
        with (logs/(tag+'.stdout')).open('wb') as stdout,(logs/(tag+'.stderr')).open('wb') as stderr:
            process=subprocess.run([str(crop['checker']),str(work/'mono.f32'),str(work/'coefficients.f64'),
                str(crop['original']),str(model),str(folder)],stdout=stdout,stderr=stderr,check=False)
        retained=retain(folder,bulk,tag) if folder.exists() else {}
        if not (folder/'summary.json').is_file():
            raise RuntimeError(f'{tag}: exit {process.returncode}, no summary; see captured logs')
        paired=crop_identity(folder,cached,original,open_notes,len(mono))
        paired.update(native_exit=process.returncode,bulk=retained)
        if process.returncode or not paired['passed']:
            return dict(formats={str(f):dict(state='crop_identity_failed',integration_pass=False)
                for f in LAB['sample_formats']},crop_identity=paired,cross_format_generated_identity=False,integration_pass=False)
    for sample_format in LAB['sample_formats']:
        key=str(sample_format);tag=name+'-'+key;folder=work/key
        with (logs/(tag+'.stdout')).open('wb') as stdout,(logs/(tag+'.stderr')).open('wb') as stderr:
            process=subprocess.run([str(harness),str(work/'mono.f32'),str(work/'coefficients.f64'),
                str(model),str(folder),key],stdout=stdout,stderr=stderr,check=False)
        if not (folder/'summary.json').is_file():
            raise RuntimeError(f'{tag}: exit {process.returncode}, no summary; see captured logs')
        summary=json.loads((folder/'summary.json').read_text())
        row=dict(native_exit=process.returncode,component=summary,bulk=retain(folder,bulk,tag))
        formats[key]=row
        if process.returncode or not summary['execution_pass']:
            row.update(state='component_execution_failed',integration_pass=False)
            continue
        generated=table(folder/'generated.tsv',['frame','note','on','source_end','ready_ns'])
        delivered=table(folder/'delivered.tsv',['note','on','host_sample','emitted_ns','cleanup'])
        callbacks=table(folder/'callbacks.tsv',['source_end','samples','started_ns','duration_ns','late_ns','allocations','frees'])
        workers=table(folder/'worker.tsv',['source_end','queued_ns','service_ns','model_ns'])
        native_sequence=sequence(generated);sequences[key]=native_sequence
        if any(r['frame']>=len(cached['frames']) or r['source_end']!=int(cached['frames'][r['frame'],3]) for r in generated):
            raise ValueError('Generated frame/source mapping differs')
        events,audit=join_delivery(generated,delivered,len(mono))
        row['identity_gates']=dict(original_generated_sequence=native_sequence==original,
            generated_delivery_and_pairing=True,original_eof_owners=audit['cleanup_notes']==open_notes,
            all_source_samples=summary['source_received']==summary['consumed_samples']==len(mono),
            dry_identity=summary['dry_identical'],vst3_event_contract=summary['event_contract'],
            sink_empty=summary['sink_active_after_cleanup']==0,
            finish_zero_allocations=summary['finish_allocations']==summary['finish_deallocations']==0,
            no_queue_or_delivery_faults=all(summary[k]==0 for k in ('input_drops','output_drops','delivery_faults')))
        row['timing']=timing_report(callbacks,workers)
        row['integration_pass']=all(row['identity_gates'].values()) and all(row['timing']['gates'].values())
        # Labels are read only after the actual component execution has ended.
        labels=read_labels(inputs/'corpus'/(name+'.tsv'));clock=dict(sample_count=len(mono),sample_rate=rate)
        require_identity(score(baseline['pitch_spans'],labels,**clock),baseline['measurement'],name+' CURRENT')
        require_identity(score(emission_spans(saved['events'],'emitted_ns',len(mono))[0],labels,**clock),
                         reference['measurement'],name+' Python causal reference')
        diagnostic=[dict(e,available_ns=ceil_div(r['source_end']*NS,rate),emitted_ns=r['ready_ns'])
                    for e,r in zip(native_sequence,generated)]
        row['views']={}
        for view,values,clock_key in (('component_delivery',events,'emitted_ns'),
            ('worker_ready',diagnostic,'emitted_ns'),('zero_compute',diagnostic,'available_ns')):
            spans,event_audit=emission_spans(values,clock_key,len(mono))
            measured=score(spans,labels,**clock)
            row['views'][view]=dict(measurement=measured,event_audit=event_audit,
                comparison_to_current=compare(baseline['measurement'],measured),
                comparison_to_python_causal=compare(reference['measurement'],measured),
                comparison_to_offline=compare(references['offline']['datasets'][name],measured))
        row['compact']={k:compact_measurement(v['measurement']) for k,v in row['views'].items()}
        row.update(state='measured',delivery_audit=audit)
    return dict(formats=formats,crop_identity=paired,cross_format_generated_identity=len(sequences)==2 and sequences['32']==sequences['64'],
        integration_pass=all(r['integration_pass'] for r in formats.values()) and len(sequences)==2 and sequences['32']==sequences['64'])


def run(spec_path,inputs,model_checkout,harness,bundle,output,cropped_model=None,crop_checker=None,crop_report=None):
    remote_only()
    output.mkdir(parents=True,exist_ok=False)
    folders={k:output/k for k in ('report','logs','cache','scratch','bulk')}
    for path in folders.values(): path.mkdir()
    report_path=folders['report']/'report.json'
    report=dict(schema='m3_neural_lab_component_v1',state='running',final=False,datasets={},
        started_at=datetime.now(timezone.utc).isoformat(),installed_output_changed=False,promotion_accepted=False)
    try:
        spec=json.loads(spec_path.read_text());root=Path(__file__).resolve().parents[1]
        source=captured_text(['git','-C',str(root),'rev-parse','HEAD'])
        if (source!=os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY')!=spec['worker_repository']
                or spec['streaming_settings']!=SETTINGS or spec['lab_settings']!=LAB or spec['native_settings']!=NATIVE
                or os.environ.get('INPUT_SHA256')!=spec['input_bundle_sha256']
                or set(spec['datasets'])!={'ordinary','extended-middle'}):
            raise ValueError('Dispatch or frozen configuration differs')
        if captured_text(['git','-C',str(model_checkout),'rev-parse','HEAD'])!=spec['model']['commit']:
            raise ValueError('Model revision differs')
        model=model_checkout/spec['model']['path'];check_hash(model,spec['model']['sha256'])
        resources=bundle/'Contents/Resources'
        crop=None
        if any(v is not None for v in (cropped_model,crop_checker,crop_report)):
            if not all(v is not None for v in (cropped_model,crop_checker,crop_report)) or spec.get('crop_settings')!=CROP:
                raise ValueError('Incomplete or unfrozen crop configuration')
            exported=json.loads(crop_report.read_text())
            if (exported['schema']!=CROP_SCHEMA or exported['parent_sha256']!=PARENT_SHA256
                    or not all(exported[k] is True for k in ('full_front_end_unchanged','weights_unchanged','onnx_check_pass'))):
                raise ValueError('Invalid model crop provenance')
            check_hash(cropped_model,exported['derived_sha256'])
            check_hash(resources/'nmp.onnx',exported['derived_sha256'])
            crop=dict(checker=crop_checker,original=model);model=cropped_model
            report['crop_export']=exported
            report['crop_checker_sha256']=digest(crop_checker)
        else:
            if 'crop_settings' in spec: raise ValueError('Crop specification requires paired checker')
            check_hash(resources/'nmp.onnx',spec['model']['sha256'])
        expected_filter=CausalResampler().h.astype('<f8').tobytes()
        if (resources/'coefficients.f64').read_bytes()!=expected_filter:
            raise ValueError('Packaged resampler differs from frozen causal filter')
        check_hash(inputs/'recovery-inputs.json',spec['input_manifest_sha256'])
        references={}
        for name,pin in spec['references'].items():
            path=root/pin['path'];check_hash(path,pin['sha256']);references[name]=json.loads(path.read_text())
        for name,config in spec['datasets'].items():
            for ext,key in (('wav','wav_sha256'),('tsv','labels_sha256')):
                check_hash(inputs/'corpus'/(name+'.'+ext),config[key])
        inventory={str(p.relative_to(bundle)):dict(bytes=p.stat().st_size,sha256=digest(p))
                   for p in sorted(bundle.rglob('*')) if p.is_file() and not p.is_symlink()}
        report['provenance']=dict(source_commit=source,worker_commit=os.environ['GITHUB_SHA'],
            worker_repository=os.environ['GITHUB_REPOSITORY'],run_id=os.environ['GITHUB_RUN_ID'],
            run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],specification=spec,specification_sha256=digest(spec_path),
            native_executable_sha256=digest(harness),ort_sdk_archive_sha256=os.environ['ORT_SDK_SHA256'],
            bundle_files=inventory,platform=platform.platform(),cpu_before=cpu_metadata())
        report['interpretation']=('Actual experimental VST3 component, paced 96 kHz variable 32/512/1024 blocks, both sample formats. '
            'Model weights, readout and decoder frozen; any graph crop is recorded separately. Original generated events must agree exactly. Primary quality uses actual sink wall-clock timestamps, '
            'not source offsets or backdating. Callback timing excludes pacing sleep and logging; lateness is separate. '
            'Allocation probes cover executable C calls and interposed C++ allocations, not all shared-library C calls. '
            'Accepting component test host and separate bundled-module smoke are not external DAW/device or hardware verification. '
            'Pitch-only output has no string assignment, MPE, bend or same-pitch unison proof. '
            'All labels retained. Integration feasibility and strict pitch replacement are separate; installed output unchanged.')
        save_json(report_path,report)
        report['artifact']=fetch_artifact(spec['worker_repository'],spec['artifact'],folders['cache']/'stream',folders['logs'])
        for name,config in spec['datasets'].items():
            report['stage']=name;save_json(report_path,report)
            report['datasets'][name]=measure(name,config,references,inputs,folders['cache']/'stream',model,harness,
                folders['scratch'],folders['logs'],folders['bulk'],crop=crop)
            save_json(report_path,report)
        rows=report['datasets'];quality_by_format={}
        for fmt in ('32','64'):
            measured=all(r['formats'][fmt].get('state')=='measured' for r in rows.values())
            quality_by_format[fmt]=(measured and rows['ordinary']['formats'][fmt]['views']['component_delivery']['comparison_to_current']['pitch_coverage_gain_pp']>=5
                and all(r['formats'][fmt]['views']['component_delivery']['comparison_to_current']['no_pitch_safety_regression'] for r in rows.values()))
        report.update(state='completed',final=True,stage='one component pass per recording and sample format complete',
            screen=dict(component_integration_pass=all(r['integration_pass'] for r in rows.values()),
                strict_pitch_replacement_by_format=quality_by_format,
                strict_pitch_replacement_pass=all(quality_by_format.values()),promotion_accepted=False))
    except Exception as error:
        report.update(state='failed',final=True,error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['cpu_after']=cpu_metadata()
        report['finished_or_updated_at']=datetime.now(timezone.utc).isoformat();save_json(report_path,report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('spec-path','inputs','model-checkout','harness','bundle','output'):
        parser.add_argument('--'+arg,type=Path,required=True)
    for arg in ('cropped-model','crop-checker','crop-report'):
        parser.add_argument('--'+arg,type=Path)
    result=run(**vars(parser.parse_args(argv)))
    print(json.dumps(dict(state=result['state'],screen=result.get('screen'),datasets={
        k:{f:r.get('compact',r.get('state')) for f,r in v['formats'].items()} for k,v in result['datasets'].items()}),allow_nan=False))
    return 0 if result.get('screen',{}).get('component_integration_pass') is True else 1


if __name__=='__main__':
    raise SystemExit(main())
