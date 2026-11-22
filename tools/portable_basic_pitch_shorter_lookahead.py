"""One frozen causal readout166 contrast; recordings and models run on GitHub.

Same adapted weights, input size, resampler, decoder and CPU runtime. This is
fresh inference with less right context, never a shift of saved events.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

import numpy as np

from tools.basic_pitch_streaming import SETTINGS
from tools.basic_pitch_temporal_crop import crop_model, compare_readout
from tools.pitch_detector_comparison import compare, digest, read_labels, score
from tools.portable_basic_pitch_cached_diagnosis import require_identity
from tools.portable_basic_pitch_comparison import check_hash, remote_only, save_json
from tools.portable_basic_pitch_graph_optimization import compare_tapes, runtime_gates
from tools.portable_basic_pitch_onnx_export import collect_reference
from tools.portable_basic_pitch_streaming import measure, StreamingBackend
from tools.portable_basic_pitch_temporal_crop import ReadoutBackend
from tools.portable_basic_pitch_trainability import synthetic_inputs
from tools.portable_direct_spectrum_learning import fetch_release


ARMS = {'control164': (164, 'cropped'), 'reference166': (166, 'original'),
        'candidate166': (166, 'cropped')}


def validate_spec(spec):
    if (spec['streaming'] != SETTINGS or spec['max_absolute'] != 1e-4
            or spec['arms'] != list(ARMS)
            or spec['readouts'] != [164,166]
            or spec['onnxruntime_version'] != '1.20.1'
            or set(spec['datasets']) != {'ordinary','extended-middle'}
            or spec['service_p99_limit_ns'] != 20_000_000
            or spec['queue_max_limit_ns'] != 26_666_667):
        raise ValueError('Frozen shorter-lookahead specification differs')


def assess(datasets, synthetic_pass):
    complete = set(datasets) == {'ordinary','extended-middle'} and all(
        set(d['arms']) == set(ARMS) for d in datasets.values())
    integrity = complete and all(d['control_reference_parity']['parity_pass']
        and d['candidate_reference_parity']['parity_pass']
        and d['candidate_source_availability_scores_identical'] for d in datasets.values())
    timing = complete and all(all(runtime_gates(d['arms'][arm]['timing']).values())
        for d in datasets.values() for arm in ('control164','candidate166'))
    quality = complete and all(d['primary_comparison']['no_pitch_safety_regression']
                               for d in datasets.values())
    return dict(reference_and_crop_integrity_pass=integrity,
        cropped_cpu_feasibility_pass=timing, paired_quality_noninferiority_pass=quality,
        shorter_lookahead_screen_pass=synthetic_pass and integrity and timing and quality,
        prior_adaptation_quality_pass=False, promotion_accepted=False,
        installed_output_changed=False,
        interpretation='Paired context experiment on reused ordinary audio and held-out middle; '
            'not an installed gain. Prior adaptation and TensorFlow parity failures persist. '
            'No native allocations, host delivery, string identity or hardware proof.')


def run(spec_path, output):
    remote_only()
    spec = json.loads(spec_path.read_text())
    validate_spec(spec)
    source = subprocess.run(['git','rev-parse','HEAD'],capture_output=True,
                            text=True,check=True).stdout.strip()
    if source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
        raise ValueError('Dispatch/source mismatch')
    output.mkdir(parents=True,exist_ok=False)
    folders = {name:output/name for name in ('report','logs','cache','inputs','reference','bulk')}
    for path in folders.values():
        path.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_basic_pitch_shorter_lookahead_v1',state='running',final=False,
        started_at=datetime.now(timezone.utc).isoformat(),source_commit=source,
        worker_commit=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],
        run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],specification=spec,
        specification_sha256=digest(spec_path),installed_output_changed=False,
        promotion_accepted=False,live_readiness='not measured',models={},datasets={})
    save_json(report_path,report)
    start = time.perf_counter()
    try:
        import onnxruntime as ort
        if ort.__version__ != spec['onnxruntime_version']:
            raise ValueError('ORT version differs')
        report['environment'] = dict(python=sys.version,platform=platform.platform(),
            numpy=np.__version__,onnxruntime=ort.__version__,intra_threads=2,inter_threads=1)
        root = Path(__file__).resolve().parents[1]
        baseline_pin = spec['baseline']
        check_hash(root/baseline_pin['path'],baseline_pin['sha256'])
        baseline = json.loads((root/baseline_pin['path']).read_text())
        references = collect_reference(spec,folders)
        report['reference_collection'] = dict(artifact=spec['artifact'],members=spec['reference_members'],
            verified=True,extraction_bytes=sum(row['bytes'] for row in spec['reference_members'].values()))
        cases = synthetic_inputs(spec['synthetic'],np)
        model = references['adapted.onnx']
        cropped_models = {}
        for readout in spec['readouts']:
            cropped_path = folders['bulk']/('adapted-readout'+str(readout)+'.onnx')
            transform = crop_model(model,cropped_path,readout_start=readout)
            cropped_models[readout] = cropped_path
            original = StreamingBackend(model,disable_optimizations=True)
            cropped = ReadoutBackend(cropped_path,readout_start=readout)
            row = dict(transform=transform,model_sha256=digest(cropped_path),
                model_bytes=cropped_path.stat().st_size,synthetic={},
                backends=dict(original=original.metadata,cropped=cropped.metadata))
            for name,signal in cases.items():
                a_note,a_onset = original.predict(signal.reshape(-1))
                b_note,b_onset = cropped.predict(signal.reshape(-1))
                row['synthetic'][name] = compare_readout(
                    dict(note=a_note[readout:readout+2],onset=a_onset[readout:readout+2]),
                    dict(note=b_note,onset=b_onset),spec['max_absolute'])
            row['synthetic_parity_pass'] = all(r['parity_pass'] for r in row['synthetic'].values())
            report['models'][str(readout)] = row
            del original,cropped
            save_json(report_path,report)
        synthetic_pass = all(r['synthetic_parity_pass'] for r in report['models'].values())
        if not synthetic_pass:
            report['state'] = 'synthetic_parity_failed'
            report['screen'] = dict(shorter_lookahead_screen_pass=False,
                reason='Synthetic crop parity failed; recordings skipped',promotion_accepted=False)
            return report
        report['input_archive'] = fetch_release(spec['worker_repository'],spec['input_release'],
                                                folders['cache'],folders['inputs'],folders['logs'])
        for name,config in spec['datasets'].items():
            for suffix,key in (('.wav','wav_sha256'),('.tsv','labels_sha256')):
                check_hash(folders['inputs']/'corpus'/(name+suffix),config[key])
            labels = read_labels(folders['inputs']/'corpus'/(name+'.tsv'))
            current = score(baseline['datasets'][name]['pitch_spans'],labels,
                            sample_count=config['sample_count'],sample_rate=config['sample_rate'])
            require_identity(current,baseline['datasets'][name]['measurement'],name+' CURRENT')
            dataset = dict(arms={})
            report['datasets'][name] = dataset
            for arm in spec['arms']:
                readout,mode = ARMS[arm]
                report['stage'] = name+'_'+arm
                save_json(report_path,report)
                backend = (StreamingBackend(model,disable_optimizations=True) if mode == 'original'
                    else ReadoutBackend(cropped_models[readout],readout_start=readout))
                destination = folders['bulk']/arm
                destination.mkdir(exist_ok=True)
                measured = measure(name,config,baseline['datasets'][name],current,
                    folders['inputs'],destination,backend,readout_start=readout)
                measured.pop('comparison_to_offline')
                measured['zero_compute_diagnostic'].pop('comparison_to_offline')
                measured['runtime_gates'] = runtime_gates(measured['timing'])
                dataset['arms'][arm] = measured
                del backend
                save_json(report_path,report)
            def parity(before,after):
                return compare_tapes(before/(name+'-stream.npz'),after/(name+'-stream.npz'),
                    before/(name+'-events.json'),after/(name+'-events.json'),spec['max_absolute'])
            dataset['control_reference_parity'] = parity(folders['reference']/'adapted_onnx',
                                                         folders['bulk']/'control164')
            dataset['candidate_reference_parity'] = parity(folders['bulk']/'reference166',
                                                           folders['bulk']/'candidate166')
            control,reference,candidate = (dataset['arms'][arm] for arm in ARMS)
            dataset['candidate_source_availability_scores_identical'] = (
                reference['zero_compute_diagnostic']['measurement']
                == candidate['zero_compute_diagnostic']['measurement'])
            dataset['primary_comparison'] = compare(control['measurement'],candidate['measurement'])
            dataset['source_availability_comparison'] = compare(
                control['zero_compute_diagnostic']['measurement'],
                candidate['zero_compute_diagnostic']['measurement'])
            save_json(report_path,report)
        report['screen'] = assess(report['datasets'],synthetic_pass)
        report['state'] = 'complete'
        return report
    except Exception as error:
        report['state'] = 'failed'
        report['error'] = dict(type=type(error).__name__,message=str(error))
        raise
    finally:
        report['final'] = True
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report['elapsed_seconds'] = time.perf_counter()-start
        report['peak_resident_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        save_json(report_path,report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    result = run(args.spec,args.output)
    print(json.dumps(dict(state=result['state'],screen=result.get('screen'))))
