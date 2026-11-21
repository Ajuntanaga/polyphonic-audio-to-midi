"""One GHA input-level observation against pinned, already generated MIDI.

No inference, native replay, parameter sweep or installed change. The resulting
lossless ceiling is an optimistic descriptive bound, not an executable policy.
"""
import argparse
import csv
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path

from tools.basic_pitch_streaming import emission_spans
from tools.neural_input_level import (FEATURES, CLASSES, causal_levels,
    occupancy_by_level, histogram, lossless_ceiling)
from tools.pitch_detector_comparison import digest, read_labels, score
from tools.portable_basic_pitch_cached_diagnosis import fetch_artifact
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.portable_neural_lab import join_delivery


def integer_table(path, columns):
    with gzip.open(path, 'rt', newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        if reader.fieldnames != columns:
            raise ValueError('Saved table header differs: ' + path.name)
        rows = [{key:int(value) for key,value in row.items()} for row in reader]
    if any(value < 0 for row in rows for value in row.values()):
        raise ValueError('Negative saved clock/count')
    return rows


def measure(name, config, inputs, evidence, reference, bulk):
    remote_only()
    import numpy as np
    import soundfile as sf

    corpus = inputs/'corpus'
    for ext,key in (('wav','wav_sha256'), ('tsv','labels_sha256')):
        check_hash(corpus/(name+'.'+ext),config[key])
    mono, rate = sf.read(str(corpus/(name+'.wav')), dtype='float32', always_2d=True)
    mono = mono.mean(axis=1, dtype=np.float32)
    if rate != config['sample_rate'] or len(mono) != config['sample_count']:
        raise ValueError('Frozen waveform clock differs')
    path = lambda suffix: evidence/(name+'-32-'+suffix+'.tsv.gz')
    callbacks = integer_table(path('callbacks'),
        ['source_end','samples','started_ns','duration_ns','late_ns','allocations','frees'])
    generated = integer_table(path('generated'), ['frame','note','on','source_end','ready_ns'])
    delivered = integer_table(path('delivered'), ['note','on','host_sample','emitted_ns','cleanup'])
    levels = causal_levels(mono, callbacks, rate)
    del mono
    # Annotations have no effect on the level extractor or saved detector output.
    labels = read_labels(corpus/(name+'.tsv'))
    events, audit = join_delivery(generated,delivered,config['sample_count'])
    spans, pairing = emission_spans(events,'emitted_ns',config['sample_count'])
    measured = score(spans,labels,sample_count=config['sample_count'],sample_rate=rate)
    expected = reference['neural']['views']['component_delivery']['measurement']
    if measured != expected:
        raise ValueError('Complete saved measurement identity failed: '+name)
    rows = occupancy_by_level(spans,labels,levels,config['sample_count'])
    totals = {kind:sum(row[kind] for row in rows) for kind in CLASSES}
    pitch = measured['pitch_sets']
    wanted = dict(genuine=pitch['totals']['present_pitch_samples'],
        wrong=pitch['totals']['extra_pitch_voice_samples'],gap=pitch['unlabeled_gap_voice_samples'])
    if totals != wanted:
        raise ValueError('Level partition does not reconcile: '+name)
    target = bulk/(name+'-causal-input-level.tsv.gz')
    with gzip.open(target,'wt',newline='') as stream:
        columns = ['start','end','source_end',*FEATURES,*CLASSES]
        writer = csv.DictWriter(stream,fieldnames=columns,delimiter='\t')
        writer.writeheader(); writer.writerows(rows)
    current = reference['current']['measurement']['pitch_sets']
    return rows,dict(sample_rate=rate,sample_count=config['sample_count'],
        gates=dict(complete_saved_measurement_identity=True,complete_occupancy_partition=True,
                   full_callback_source_coverage=True,causal_level_updates=True),
        callback_count=len(callbacks),level_intervals=len(levels),delivery_audit=audit,event_audit=pairing,
        neural_totals=totals,
        current_totals=dict(genuine=current['totals']['present_pitch_samples'],
            wrong=current['totals']['extra_pitch_voice_samples'],gap=current['unlabeled_gap_voice_samples']),
        histograms={feature:histogram(rows,feature) for feature in FEATURES},
        bulk=dict(name=target.name,bytes=target.stat().st_size,sha256=digest(target)))


def run(spec_path, inputs, output):
    remote_only()
    output.mkdir(parents=True,exist_ok=False)
    folders = {key:output/key for key in ('report','logs','scratch','bulk')}
    for folder in folders.values(): folder.mkdir()
    target = folders['report']/'report.json'
    report = dict(schema='m3_neural_input_level_v1',state='running',final=False,datasets={},
        started_at=datetime.now(timezone.utc).isoformat(),installed_output_changed=False,
        promotion_accepted=False)
    try:
        spec = json.loads(spec_path.read_text())
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git','-C',str(root),'rev-parse','HEAD'])
        if (spec['schema'] != 'm3_neural_input_level_spec_v1'
                or source != os.environ.get('SOURCE_SHA')
                or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']
                or os.environ.get('INPUT_SHA256') != spec['input_bundle_sha256']
                or spec['features'] != list(FEATURES)):
            raise ValueError('Frozen dispatch configuration differs')
        check_hash(inputs/'recovery-inputs.json',spec['input_manifest_sha256'])
        report['provenance'] = dict(source_sha=source,worker_sha=os.environ['GITHUB_SHA'],
            run_id=os.environ['GITHUB_RUN_ID'],spec_sha256=digest(spec_path),
            reference_run=spec['reference_run'],waveform_gain='1.0; same mono mean float32 as Neural Lab')
        paths = {}
        report['artifacts'] = {}
        for kind,config in spec['artifacts'].items():
            paths[kind] = folders['scratch']/kind
            report['artifacts'][kind] = fetch_artifact(spec['worker_repository'],config,paths[kind],folders['logs'])
        reference = json.loads((paths['report']/'report.json').read_text())
        all_rows = {}
        for name,config in spec['datasets'].items():
            rows,result = measure(name,config,inputs,paths['evidence'],reference['datasets'][name],folders['bulk'])
            all_rows[name] = rows
            report['datasets'][name] = result
            save_json(target,report)
            print(json.dumps(dict(dataset=name,totals=result['neural_totals'],gates=result['gates'])),flush=True)
        report['lossless_bounds'] = {}
        for feature in FEATURES:
            bound = lossless_ceiling(all_rows,feature)
            for name,removable in bound['datasets'].items():
                row = report['datasets'][name]
                removable['remaining_gap'] = row['neural_totals']['gap'] - removable['gap']
                removable['remaining_wrong'] = row['neural_totals']['wrong'] - removable['wrong']
                removable['gap_delta_to_current'] = removable['remaining_gap'] - row['current_totals']['gap']
                removable['wrong_delta_to_current'] = removable['remaining_wrong'] - row['current_totals']['wrong']
            bound['all_gap_growth_removable'] = all(row['gap_delta_to_current'] <= 0 for row in bound['datasets'].values())
            report['lossless_bounds'][feature] = bound
        primary = report['lossless_bounds']['power_max']
        report.update(state='completed',final=True,
            verdict='occupancy_bound_sufficient_for_gap_growth' if primary['all_gap_growth_removable']
                    else 'primary_level_gate_cannot_remove_all_gap_growth_without_genuine_loss',
            limitations=spec['limitations'])
    except Exception as error:
        report.update(state='error',final=True,error=repr(error))
        raise
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        save_json(target,report)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec',type=Path,required=True)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    run(args.spec,args.inputs,args.output)


if __name__ == '__main__': main()
