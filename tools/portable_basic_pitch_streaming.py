"""One fixed causal Basic Pitch CPU feasibility pass; GitHub Actions only."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import time

from tools.basic_pitch_streaming import (SETTINGS, emission_spans, stream_blocks,
                                         timing_summary, ceil_div, NS)
from tools.pitch_detector_comparison import compare, digest, read_labels, score
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json


class StreamingBackend:
    def __init__(self, model_path, *, disable_optimizations=False):
        remote_only()
        import numpy as np
        import onnxruntime as ort
        import soundfile as sf
        self.np, self.sf = np, sf
        options = ort.SessionOptions()
        options.intra_op_num_threads = SETTINGS['intra_op_threads']
        options.inter_op_num_threads = SETTINGS['inter_op_threads']
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        if disable_optimizations:
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        self.session = ort.InferenceSession(str(model_path), sess_options=options,
                                            providers=['CPUExecutionProvider'])
        if self.session.get_providers() != ['CPUExecutionProvider']:
            raise ValueError('CPU-only session required')
        inputs = self.session.get_inputs()
        outputs = {r.name for r in self.session.get_outputs()}
        if (len(inputs) != 1 or inputs[0].name != 'serving_default_input_2:0'
                or not {'StatefulPartitionedCall:1','StatefulPartitionedCall:2'} <= outputs):
            raise ValueError('Pinned ONNX interface mismatch')
        start = time.perf_counter_ns()
        self.predict(np.zeros(43844, dtype=np.float32))
        self.metadata = dict(onnxruntime_version=ort.__version__, numpy_version=np.__version__,
            providers=self.session.get_providers(), warmup='One all-zero window; excluded from service',
            warmup_ns=time.perf_counter_ns()-start, intra_op_threads=2, inter_op_threads=1,
            execution_mode='sequential', graph_optimizations='disabled' if disable_optimizations else 'all',
            input_name=inputs[0].name,
            note_output='StatefulPartitionedCall:1', onset_output='StatefulPartitionedCall:2')

    def predict(self, window):
        outputs = self.session.run(['StatefulPartitionedCall:1','StatefulPartitionedCall:2'],
            {'serving_default_input_2:0': window.reshape(1,43844,1).astype(self.np.float32, copy=False)})
        return outputs[0][0], outputs[1][0]


def assess(datasets):
    primary = [r['comparison_to_current'] for r in datasets.values()]
    gain = datasets['ordinary']['comparison_to_current']['pitch_coverage_gain_pp']
    strict = gain >= 5 and all(r['no_pitch_safety_regression'] for r in primary)
    retained = {}
    for band in ('60to71','72plus'):
        row = datasets['ordinary']['comparison_to_offline']['label_bands'][band]
        baseline = row['current_present_label_samples']
        ratio = row['model_present_label_samples']/baseline if baseline else None
        retained[band] = dict(ratio_to_offline_present_time=ratio,
                             at_least_75_percent=ratio is not None and ratio >= .75)
    realtime = {}
    for name, row in datasets.items():
        timing = row['timing']
        realtime[name] = dict(
            service_p99_under_20ms=timing['inference_block_service_ns']['p99'] <= 20_000_000,
            maximum_queued_backlog_under_26_667ms=timing['queued_before_service_ns']['maximum'] <= 26_666_667)
    return dict(strict_replacement_screen_pass=strict, ordinary_coverage_gain_pp= gain,
        upper_band_retention_indicators=retained, cpu_feasibility_indicators=realtime,
        promotion_accepted=False, installed_output_changed=False,
        interpretation='One fixed-context distinct-pitch prototype. Feasibility indicators '
            'do not override strict losses and do not establish native/host/live acceptance.')


def measure(name, config, reference, offline, inputs, bulk, backend, context_cache=None):
    remote_only()
    wav = inputs/'corpus'/(name+'.wav')
    info = backend.sf.info(str(wav))
    if info.samplerate != config['sample_rate'] or info.frames != config['sample_count']:
        raise ValueError('Audio clock differs from specification')
    print(f'{name}: causal pass starting', flush=True)
    with backend.sf.SoundFile(str(wav)) as audio:
        def chunks():
            while True:
                chunk = audio.read(640, dtype='float32', always_2d=True)
                if not len(chunk):
                    return
                yield chunk
        result = stream_blocks(chunks(), backend,
            progress=lambda calls, samples: print(f'{name}: {calls} windows, {samples}/{info.frames} samples', flush=True),
            additional_readout_start=160 if context_cache is not None else None)
    if result['source_samples'] != info.frames:
        raise ValueError('Incomplete source consumption')
    if not result['model_calls']:
        raise ValueError('No model output; cannot score a silent failure')
    artifact = bulk/(name+'-stream.npz')
    backend.np.savez_compressed(artifact, note=result['notes'], onset=result['onsets'],
        frames=backend.np.asarray(result['frames'], dtype='int64'),
        timing=backend.np.asarray(result['timing'], dtype='int64'))
    events_path = bulk/(name+'-events.json')
    cleanup_ns = max(ceil_div(info.frames*NS, info.samplerate),result['worker_finish_ns'])
    save_json(events_path, dict(events=result['events'],
        cleanup=dict(emitted_ns=cleanup_ns, notes=result['open_decoder_pitches'],
            scope='Explicit end-of-stream release, separate from detector decisions and score clipping'),
        frame_columns=['frame','nominal_model_sample','window_end_exclusive','arrived_source_samples'],
        timing_columns=['source_end','arrival_ns','service_ns','finish_ns','queued_ns',
                        'resample_and_buffer_ns','model_ns','decode_ns','model_called']))
    # No annotation values enter inference, decoder or scheduling.
    labels = read_labels(inputs/'corpus'/(name+'.tsv'))
    clock = dict(sample_count=info.frames, sample_rate=info.samplerate)
    views = {}
    for label, time_key in (('serviced','emitted_ns'),('zero_compute','available_ns')):
        spans, audit = emission_spans(result['events'], time_key, info.frames)
        measured = score(spans, labels, **clock)
        views[label] = dict(measurement=measured, event_audit=audit,
            comparison_to_current=compare(reference['measurement'], measured),
            comparison_to_offline=compare(offline, measured))
    measured_result = dict(audio=dict(**clock,channels=info.channels,subtype=info.subtype),
        **views['serviced'], zero_compute_diagnostic=views['zero_compute'],
        timing=timing_summary(result['timing']), model_calls=result['model_calls'],
        observed_output_frames=len(result['frames']), resampled_samples=result['resampled_samples'],
        next_window_end_exclusive=result['next_window_end'],
        open_decoder_pitches_at_end=result['open_decoder_pitches'],
        cleanup_emitted_ns=cleanup_ns, worker_finish_ns=result['worker_finish_ns'],
        bulk={p.name:dict(bytes=p.stat().st_size,sha256=digest(p)) for p in (artifact,events_path)})
    if context_cache is not None:
        from tools.basic_pitch_context import save_context
        measured_result['context_candidate'] = save_context(name,result,labels,clock,
            reference['measurement'],offline,bulk,context_cache)
    return measured_result


def run(spec_path, inputs, model_checkout, output):
    remote_only()
    output.mkdir(parents=True, exist_ok=False)
    report_dir, bulk = output/'report', output/'bulk'
    report_dir.mkdir()
    bulk.mkdir()
    report_path = report_dir/'report.json'
    report = dict(schema='m3_basic_pitch_streaming_v1',state='running',final=False,
        started_at=datetime.now(timezone.utc).isoformat(),datasets={},
        installed_output_changed=False,promotion_accepted=False,live_readiness='not measured')
    try:
        spec = json.loads(spec_path.read_text())
        if spec['streaming'] != SETTINGS:
            raise ValueError('Implementation settings differ from frozen specification')
        context_cache = None
        if 'paired_context' in spec:
            from tools.basic_pitch_context import CONTEXT
            if spec['paired_context'] != CONTEXT:
                raise ValueError('Context candidate differs from frozen specification')
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git','-C',str(root),'rev-parse','HEAD'])
        if source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
            raise ValueError('Source or worker dispatch pin mismatch')
        upstream = captured_text(['git','-C',str(model_checkout),'rev-parse','HEAD'])
        if upstream != spec['model']['commit']:
            raise ValueError('Upstream model source pin mismatch')
        model_path = model_checkout/spec['model']['path']
        check_hash(model_path,spec['model']['sha256'])
        baseline_path, offline_path = root/spec['baseline_file'], root/spec['offline_reference_file']
        check_hash(baseline_path,spec['baseline_sha256'])
        check_hash(offline_path,spec['offline_reference_sha256'])
        baseline, offline = json.loads(baseline_path.read_text()),json.loads(offline_path.read_text())
        check_hash(inputs/'recovery-inputs.json',spec['input_manifest_sha256'])
        if os.environ.get('INPUT_SHA256') != spec['input_bundle_sha256']:
            raise ValueError('Input bundle pin mismatch')
        if set(spec['datasets']) != {'ordinary','extended-middle'}:
            raise ValueError('Both fixed recordings are required')
        for name, config in spec['datasets'].items():
            for ext,key in (('wav','wav_sha256'),('tsv','labels_sha256')):
                check_hash(inputs/'corpus'/(name+'.'+ext),config[key])
            saved = baseline['datasets'][name]
            if (saved['raw_midi_sha256'] != config['baseline']['raw_midi_sha256']
                    or saved['source_commit'] != config['baseline']['source_commit']
                    or saved['run_id'] != config['baseline']['run_id']
                    or saved['labels_sha256'] != config['labels_sha256']):
                raise ValueError('Saved CURRENT baseline mismatch')
        report['provenance'] = dict(source_commit=source,worker_commit=os.environ['GITHUB_SHA'],
            worker_repository=os.environ['GITHUB_REPOSITORY'],run_id=os.environ['GITHUB_RUN_ID'],
            run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],specification_sha256=digest(spec_path),
            specification=spec,python=sys.version,platform=platform.platform())
        report['scope'] = dict(primary_clock='Single FIFO worker completion, ceil to source sample',
            diagnostic_clock='Input block availability, same events with zero compute delay',
            service='Resample, buffer/window, model, validation, decoder; excludes file/evidence I/O',
            no_claims=['native allocations/deadlines','physical attack latency','DAW/device delivery',
                       'string/unison assignment','replucks/bends','installed note gain'])
        (report_dir/'environment.txt').write_text(captured_text([sys.executable,'-m','pip','freeze','--all'])+'\n')
        if 'paired_context' in spec:
            from tools.portable_basic_pitch_cached_diagnosis import fetch_artifact
            context_cache = output/'reference-cache'
            logs = output/'logs'
            logs.mkdir()
            report['reference_artifact'] = fetch_artifact(spec['worker_repository'],
                spec['stream_reference_artifact'],context_cache,logs)
            report['scope']['service'] += '; paired context includes BOTH independent decoders'
            report['schema'] = 'm3_basic_pitch_paired_context_v1'
        backend = StreamingBackend(model_path)
        report['backend'] = backend.metadata
        for name,config in spec['datasets'].items():
            report['stage'] = name
            save_json(report_path,report)
            report['datasets'][name] = measure(name,config,baseline['datasets'][name],
                offline['datasets'][name],inputs,bulk,backend,context_cache=context_cache)
            save_json(report_path,report)
        report.update(state='completed',final=True,stage='both recordings scored',screen=assess(report['datasets']))
        if context_cache is not None:
            from tools.basic_pitch_context import context_screen
            report['context_screen'] = context_screen(report['datasets'])
    except Exception as error:
        report.update(state='failed',final=True,error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_or_updated_at'] = datetime.now(timezone.utc).isoformat()
        save_json(report_path,report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec',dest='spec_path',type=Path,required=True)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--model-checkout',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    result = run(**vars(parser.parse_args()))
    print(json.dumps(dict(state=result['state'],screen=result['screen'],
        context_screen=result.get('context_screen')),allow_nan=False))
