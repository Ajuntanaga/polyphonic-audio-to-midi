"""One fixed OFF/ON optional input-gate measurement on GitHub CPU only."""
import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import subprocess

from tools.basic_pitch_cached_diagnosis import compact_measurement
from tools.basic_pitch_streaming import CausalResampler, SETTINGS, emission_spans, ceil_div, NS
from tools.neural_crop_model import SCHEMA as CROP_SCHEMA, PARENT_SHA256
from tools.pitch_detector_comparison import compare, digest, read_labels, score
from tools.portable_basic_pitch_cached_diagnosis import fetch_artifact
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.portable_basic_pitch_native import NATIVE, retain, sequence, table
from tools.portable_neural_corpus import CORPUS, CORPUS_LAB, MODEL_SHA256
from tools.portable_neural_input_level import integer_table
from tools.portable_neural_lab import LAB, join_delivery, timing_report
from tools.portable_neural_ort_diagnosis import cpu_metadata


GATE = dict(default_enabled=False, threshold_dbfs=-60.0, reopen_margin_db=6.0,
            windows_samples=[1920,7680], close_dwell_samples=3840,
            feature='maximum trailing mean-square power; observed-sample startup',
            release='decoder-owned NoteOff at next model readout',
            control='latched at first sample of each source packet')
GENERATED_COLUMNS = ['frame','note','on','source_end','ready_ns']
ARMS = ('off','on')
PRIMARY = ('ordinary','extended-middle')


def generated_identity(actual, expected):
    """Source-clock MIDI identity; machine scheduling timestamps are excluded."""
    keys = GENERATED_COLUMNS[:-1]
    a = [tuple(row[key] for key in keys) for row in actual]
    b = [tuple(row[key] for key in keys) for row in expected]
    first = next((i for i,(x,y) in enumerate(zip(a,b)) if x != y), None)
    if first is None and len(a) != len(b): first = min(len(a),len(b))
    return dict(pass_=a==b, fields=keys, actual_count=len(a), reference_count=len(b),
                first_difference_index=first)


def gate_audit(path, generated, summary, enabled, sample_count):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        if reader.fieldnames != ['source_end','frame','power','enabled','open']:
            raise ValueError('Gate evidence schema differs')
        rows = [dict(source_end=int(r['source_end']),frame=int(r['frame']),power=float(r['power']),
                     enabled=int(r['enabled']),open=int(r['open'])) for r in reader]
    if len(rows) != summary['model_calls']:
        raise ValueError('Gate evidence does not cover all model calls')
    previous = 0
    for i,row in enumerate(rows):
        if (row['frame'] != 2*i or not previous < row['source_end'] <= sample_count
                or not math.isfinite(row['power']) or row['power'] < 0
                or row['enabled'] != int(enabled) or row['open'] not in (0,1)
                or (not enabled and (row['open'] != 1 or row['power'] != 0))):
            raise ValueError('Invalid gate frame, level or state')
        previous = row['source_end']
    forced_releases = 0
    for event in generated:
        index = event['frame']//2
        if index >= len(rows) or rows[index]['source_end'] != event['source_end']:
            raise ValueError('MIDI event lacks matching gate observation')
        if not rows[index]['open']:
            if event['on']: raise ValueError('Closed gate generated a NoteOn')
            forced_releases += 1
    closed = sum(not row['open'] for row in rows)*2
    if (closed != summary['gate_closed_frames']
            or forced_releases != summary['gate_forced_releases']
            or summary['gate_enabled'] != enabled or summary['gate_threshold_db'] != GATE['threshold_dbfs']):
        raise ValueError('Gate mechanism counters differ')
    return dict(pass_=True, readouts=len(rows), closed_frames=closed,
                forced_releases=forced_releases,
                state_changes=sum(a['open'] != b['open'] for a,b in zip(rows,rows[1:])))


def note_on_counts(events, labels, rate):
    """Actual accepted NoteOns, separate from merged pitch-occupancy segments."""
    ons = [(ceil_div(e['emitted_ns']*rate,NS),e['note']) for e in events if e['kind']=='on']
    return dict(total=len(ons), labels=[dict(label_index=row['label_index'],midi_note=row['midi_note'],
        accepted_note_ons=sum(note==row['midi_note'] and row['start_sample']<=sample<row['end_sample']
                             for sample,note in ons)) for row in labels])


def evaluate(folder, exit_code, enabled, config, labels, current, reference_generated, bulk, tag):
    summary = json.loads((folder/'summary.json').read_text())
    row = dict(native_exit=exit_code,component=summary,bulk=retain(folder,bulk,tag),
               integration_pass=False,quality_pass=False)
    if exit_code or not summary['execution_pass']:
        row['state']='component_execution_failed'
        return row
    generated = table(folder/'generated.tsv',GENERATED_COLUMNS)
    delivered = table(folder/'delivered.tsv',['note','on','host_sample','emitted_ns','cleanup'])
    callbacks = table(folder/'callbacks.tsv',['source_end','samples','started_ns','duration_ns','late_ns','allocations','frees'])
    workers = table(folder/'worker.tsv',['source_end','queued_ns','service_ns','model_ns'])
    count,rate = config['sample_count'],config['sample_rate']
    native_sequence = sequence(generated)
    if any(r['source_end'] > count for r in generated):
        raise ValueError('Generated event refers to unavailable source samples')
    events,audit = join_delivery(generated,delivered,count)
    row['gate_audit'] = gate_audit(folder/'gate.tsv',generated,summary,enabled,count)
    row['identity_gates'] = dict(generated_delivery_and_pairing=True,
        sample_format=summary['sample_format']==32,
        all_source_samples=summary['source_samples']==summary['source_received']==summary['consumed_samples']==count,
        dry_identity=summary['dry_identical'],vst3_event_contract=summary['event_contract'],
        sink_empty=summary['sink_active_after_cleanup']==0,
        finish_zero_allocations=summary['finish_allocations']==summary['finish_deallocations']==0,
        no_queue_or_delivery_faults=all(summary[k]==0 for k in ('input_drops','output_drops','delivery_faults')),
        gate_mechanism=row['gate_audit']['pass_'])
    if not enabled:
        row['saved_generated_identity'] = generated_identity(generated,reference_generated)
        row['identity_gates']['saved_off_generated_identity'] = row['saved_generated_identity']['pass_']
    row['timing'] = timing_report(callbacks,workers)
    row['integration_pass'] = all(row['identity_gates'].values()) and all(row['timing']['gates'].values())
    diagnostic = [dict(e,available_ns=ceil_div(r['source_end']*NS,rate),emitted_ns=r['ready_ns'])
                  for e,r in zip(native_sequence,generated)]
    row['views'] = {}
    for view,values,clock_key in (('component_delivery',events,'emitted_ns'),
                                 ('worker_ready',diagnostic,'emitted_ns'),
                                 ('zero_compute',diagnostic,'available_ns')):
        spans,event_audit = emission_spans(values,clock_key,count)
        measured = score(spans,labels,sample_count=count,sample_rate=rate)
        row['views'][view] = dict(measurement=measured,event_audit=event_audit,
                                 comparison_to_current=compare(current,measured))
    row['compact'] = {key:compact_measurement(value['measurement']) for key,value in row['views'].items()}
    row.update(state='measured',delivery_audit=audit,note_ons=note_on_counts(events,labels,rate),
               quality_pass=row['views']['component_delivery']['comparison_to_current']['no_pitch_safety_regression'])
    return row


def measure(name,config,inputs,model,harness,folders,reference,evidence):
    remote_only()
    import numpy as np
    import soundfile as sf
    work = folders['scratch']/name
    work.mkdir()
    corpus = inputs/'corpus'
    mono,rate = sf.read(str(corpus/(name+'.wav')),dtype='float32',always_2d=True)
    mono = mono.mean(axis=1,dtype=np.float32)
    if rate!=config['sample_rate'] or len(mono)!=config['sample_count'] or not np.isfinite(mono).all():
        raise ValueError('Source clock or finite samples differ')
    mono.astype('<f4').tofile(work/'mono.f32')
    CausalResampler().h.astype('<f8').tofile(work/'coefficients.f64')
    exits = {}
    for arm in ARMS:
        command=[str(harness),str(work/'mono.f32'),str(work/'coefficients.f64'),str(model),str(work/arm),'32']
        if arm=='on': command.append(str(GATE['threshold_dbfs']))
        tag=name+'-'+arm
        with (folders['logs']/(tag+'.stdout')).open('wb') as stdout, (folders['logs']/(tag+'.stderr')).open('wb') as stderr:
            process=subprocess.run(command,stdout=stdout,stderr=stderr,check=False,timeout=len(mono)/rate+120)
        exits[arm]=process.returncode
        if not (work/arm/'summary.json').is_file():
            raise RuntimeError(f'{tag}: exit {process.returncode}, no summary; see captured logs')
    # No annotations are read until both causal executions have finished.
    labels=read_labels(corpus/(name+'.tsv'))
    current=reference['current']['measurement']
    if current['sample_count']!=len(mono) or current['sample_rate']!=rate:
        raise ValueError('Saved CURRENT clock differs')
    if 'pitch_spans' in reference['current']:
        reproduced=score(reference['current']['pitch_spans'],labels,sample_count=len(mono),sample_rate=rate)
        if reproduced!=current:
            raise ValueError('Saved CURRENT score does not reproduce from pinned MIDI spans')
    saved=integer_table(evidence/(name+'-32-generated.tsv.gz'),GENERATED_COLUMNS)
    result=dict(current=current,arms={})
    for arm in ARMS:
        result['arms'][arm]=evaluate(work/arm,exits[arm],arm=='on',config,labels,current,saved,
                                    folders['bulk'],name+'-'+arm)
    if all(row['state']=='measured' for row in result['arms'].values()):
        result['on_vs_off']={key:compare(result['arms']['off']['views'][key]['measurement'],
                                       result['arms']['on']['views'][key]['measurement'])
                             for key in result['arms']['off']['views']}
        a,b=(result['arms'][arm]['note_ons'] for arm in ARMS)
        result['note_on_delta']=dict(total=b['total']-a['total'],labels=[
            dict(label_index=x['label_index'],midi_note=x['midi_note'],before=x['accepted_note_ons'],
                 after=y['accepted_note_ons'],delta=y['accepted_note_ons']-x['accepted_note_ons'])
            for x,y in zip(a['labels'],b['labels'])])
    return result


def current_references(reference, spec, root):
    """Bind neural OFF identity separately from the saved M3 CURRENT scores."""
    names = tuple(spec['datasets'])
    expected_schema = ('m3_neural_lab_supplemental_corpus_v1' if names == CORPUS
                       else 'm3_neural_lab_component_v1')
    if (names not in (CORPUS, PRIMARY) or reference['schema'] != expected_schema
            or reference['final'] is not True
            or str(reference['provenance']['run_id']) != str(spec['reference_run'])
            or reference['provenance']['specification']['datasets'] != spec['datasets']
            or set(reference['datasets']) != set(names)):
        raise ValueError('Saved reference provenance differs')
    if names == CORPUS:
        return reference['datasets']
    baseline_pin = spec['current_baseline']
    path = root / baseline_pin['path']
    check_hash(path, baseline_pin['sha256'])
    baseline = json.loads(path.read_text())
    if (baseline['schema'] != 2 or baseline['method'] != 'Saved CURRENT MIDI; pitch union only'
            or set(baseline['datasets']) != set(names)):
        raise ValueError('Saved CURRENT baseline schema differs')
    result = {}
    for name, config in spec['datasets'].items():
        saved = baseline['datasets'][name]
        if (not reference['datasets'][name]['integration_pass']
                or saved['labels_sha256'] != config['labels_sha256']
                or any(saved[key] != config['baseline'][key]
                       for key in ('raw_midi_sha256','run_id','source_commit'))):
            raise ValueError('Saved CURRENT baseline provenance differs')
        result[name] = dict(current=dict(measurement=saved['measurement'],
                                        pitch_spans=saved['pitch_spans']))
    return result


def screen(rows, required=CORPUS):
    complete=set(rows)==set(required) and all(set(r.get('arms',{}))==set(ARMS) for r in rows.values())
    arms=[arm for row in rows.values() for arm in row.get('arms',{}).values()]
    return dict(arms_measured=sum(r.get('state')=='measured' for r in arms),arms_required=len(required)*2,
        component_integration_pass=complete and all(r.get('integration_pass') is True for r in arms),
        on_vs_off_lossless_pass=complete and all(r.get('on_vs_off',{}).get('component_delivery',{}).get('no_pitch_safety_regression') is True for r in rows.values()),
        on_vs_current_replacement_pass=complete and all(r['arms']['on'].get('quality_pass') is True for r in rows.values()),
        promotion_accepted=False,installed_output_changed=False)


def run(spec_path,inputs,model_checkout,harness,bundle,output,cropped_model,crop_report):
    remote_only()
    output.mkdir(parents=True,exist_ok=False)
    folders={key:output/key for key in ('report','logs','scratch','bulk')}
    for path in folders.values(): path.mkdir()
    target=folders['report']/'report.json'
    report=dict(schema='m3_neural_quiet_gate_v1',state='running',final=False,datasets={},
        started_at=datetime.now(timezone.utc).isoformat(),installed_output_changed=False,promotion_accepted=False)
    try:
        spec=json.loads(spec_path.read_text())
        root=Path(__file__).resolve().parents[1]
        source=captured_text(['git','-C',str(root),'rev-parse','HEAD'])
        if (spec['schema']!='m3_neural_quiet_gate_spec_v1' or source!=os.environ.get('SOURCE_SHA')
                or os.environ.get('GITHUB_REPOSITORY')!=spec['worker_repository']
                or spec['streaming_settings']!=SETTINGS or spec['lab_settings']!=CORPUS_LAB
                or spec['native_settings']!=NATIVE or spec['gate_settings']!=GATE
                or os.environ.get('INPUT_SHA256')!=spec['input_bundle_sha256']
                or tuple(spec['datasets']) not in (CORPUS,PRIMARY) or spec['derived_model_sha256']!=MODEL_SHA256
                or any(c['sample_rate']!=LAB['rate'] for c in spec['datasets'].values())):
            raise ValueError('Dispatch or frozen configuration differs')
        if captured_text(['git','-C',str(model_checkout),'rev-parse','HEAD'])!=spec['model']['commit']:
            raise ValueError('Model revision differs')
        check_hash(model_checkout/spec['model']['path'],spec['model']['sha256'])
        exported=json.loads(crop_report.read_text())
        if (exported['schema']!=CROP_SCHEMA or exported['parent_sha256']!=PARENT_SHA256
                or exported['derived_sha256']!=MODEL_SHA256
                or not all(exported[k] is True for k in ('full_front_end_unchanged','weights_unchanged','onnx_check_pass'))):
            raise ValueError('Invalid model crop provenance')
        resources=bundle/'Contents/Resources'
        check_hash(cropped_model,MODEL_SHA256); check_hash(resources/'nmp.onnx',MODEL_SHA256)
        if (resources/'coefficients.f64').read_bytes()!=CausalResampler().h.astype('<f8').tobytes():
            raise ValueError('Packaged resampler differs')
        check_hash(inputs/'recovery-inputs.json',spec['input_manifest_sha256'])
        for name,config in spec['datasets'].items():
            for ext,key in (('wav','wav_sha256'),('tsv','labels_sha256')):
                check_hash(inputs/'corpus'/(name+'.'+ext),config[key])
        report['provenance']=dict(source_commit=source,worker_commit=os.environ['GITHUB_SHA'],
            worker_repository=os.environ['GITHUB_REPOSITORY'],run_id=os.environ['GITHUB_RUN_ID'],
            run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],specification=spec,specification_sha256=digest(spec_path),
            harness_sha256=digest(harness),ort_sdk_archive_sha256=os.environ['ORT_SDK_SHA256'],
            platform=platform.platform(),cpu_before=cpu_metadata(),crop_export=exported,
            bundle_files={str(p.relative_to(bundle)):dict(bytes=p.stat().st_size,sha256=digest(p))
                          for p in sorted(bundle.rglob('*')) if p.is_file() and not p.is_symlink()})
        paths={};report['artifacts']={}
        for kind,config in spec['artifacts'].items():
            paths[kind]=folders['scratch']/kind
            report['artifacts'][kind]=fetch_artifact(spec['worker_repository'],config,paths[kind],folders['logs'])
        reference=json.loads((paths['report']/'report.json').read_text())
        references=current_references(reference,spec,root)
        report['interpretation']=(
            f'Optional default-off quiet-input gate; one fixed -60dBFS ON arm against OFF on each of{len(spec["datasets"])} recordings. '
            'A deliberate weak-sustain tradeoff, not a claimed lossless replacement. '
            f'OFF generated source-clock MIDI must match saved run{spec["reference_run"]}; wall scheduling is fresh. '
            'Primary quality uses accepted callback timestamps; worker-ready/zero-compute are diagnostic. '
            'Every label and per-label present/longest-hold/NoteOn delta retained. Wrong-pitch and gap extras separate. '
            'M3 CURRENT is the separately pinned saved reference, not rerun. Recorded measurements use float32. '
            'Pitch-only occupancy deduplicates unisons; no lanes, bends or MPE claim. '
            'Package/integration success is not external DAW/device acceptance; no installed/default change.')
        save_json(target,report)
        for name,config in spec['datasets'].items():
            report['stage']=name;save_json(target,report)
            report['datasets'][name]=measure(name,config,inputs,cropped_model,harness,folders,
                                             references[name],paths['evidence'])
            save_json(target,report)
            print(json.dumps(dict(dataset=name,screen=screen(report['datasets'],spec['datasets'])),allow_nan=False),flush=True)
        report.update(state='completed',final=True,stage='all specified OFF/ON pairs complete',screen=screen(report['datasets'],spec['datasets']))
    except Exception as error:
        report.update(state='failed',final=True,error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['cpu_after']=cpu_metadata()
        report['finished_or_updated_at']=datetime.now(timezone.utc).isoformat()
        save_json(target,report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('spec-path','inputs','model-checkout','harness','bundle','output','cropped-model','crop-report'):
        parser.add_argument('--'+arg,type=Path,required=True)
    result=run(**vars(parser.parse_args(argv)))
    print(json.dumps(dict(state=result['state'],screen=result.get('screen')),allow_nan=False))
    return 0 if result.get('screen',{}).get('component_integration_pass') is True else 1


if __name__=='__main__': raise SystemExit(main())
