"""One fixed GitHub CPU re-decode of pinned causal caches, without inference."""
import argparse
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import platform
import sys

from tools.basic_pitch_cached_diagnosis import (compact_measurement, decode_cached,
    labels_from_measurement)
from tools.basic_pitch_onset_decoder import (ONSET_DECODER, candidate_measurements,
    clock_events, decode_onset_cached, onset_screen)
from tools.basic_pitch_streaming import SETTINGS, emission_spans
from tools.pitch_detector_comparison import digest, score
from tools.portable_basic_pitch_cached_diagnosis import (cached_arrays, fetch_artifact,
    require_identity)
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json


def measure(name, config, baseline, stream_reference, cache, bulk):
    remote_only()
    clock = dict(sample_count=config['sample_count'], sample_rate=config['sample_rate'])
    if clock['sample_rate'] != SETTINGS['source_rate']:
        raise ValueError('Original 96000 Hz source clock is required')
    arrays = cached_arrays(cache/(name+'-stream.npz'), stream=True)
    saved = json.loads((cache/(name+'-events.json')).read_text())
    require_identity(saved['frame_columns'],
        ['frame','nominal_model_sample','window_end_exclusive','arrived_source_samples'], 'frame columns')
    require_identity(saved['timing_columns'],
        ['source_end','arrival_ns','service_ns','finish_ns','queued_ns',
         'resample_and_buffer_ns','model_ns','decode_ns','model_called'], 'timing columns')
    reference_events, reference_open = decode_cached(arrays['note'], arrays['onset'])
    reference_events = clock_events(reference_events, arrays['frames'], arrays['timing'])
    require_identity(reference_events, saved['events'], name+' reference events and clocks')
    require_identity(reference_open, saved['cleanup']['notes'], name+' reference EOF state')
    # Both decoders consume only cached model outputs. No labels reach either.
    candidate_events, candidate_open = decode_onset_cached(arrays['note'], arrays['onset'])
    candidate_events = clock_events(candidate_events, arrays['frames'], arrays['timing'])
    labels = labels_from_measurement(baseline['measurement'])
    require_identity(score(baseline['pitch_spans'], labels, **clock),
                     baseline['measurement'], name+' CURRENT measurement')
    for key, expected in (('emitted_ns', stream_reference['measurement']),
                         ('available_ns', stream_reference['zero_compute_measurement'])):
        spans, audit = emission_spans(reference_events, key, clock['sample_count'])
        require_identity(score(spans, labels, **clock), expected, name+' reference '+key)
    candidate = candidate_measurements(candidate_events, stream_reference,
        baseline['measurement'], labels, clock)
    evidence = bulk/(name+'-onset-events.json.gz')
    with gzip.open(evidence, 'wt', encoding='utf-8') as output:
        json.dump(dict(events=candidate_events,
            cleanup=dict(emitted_ns=saved['cleanup']['emitted_ns'], notes=candidate_open),
            timing_interpretation='Original measured FIFO clock reused; candidate service not measured'),
            output, allow_nan=False, separators=(',', ':'))
    return dict(full_record_identity=dict(current=True, stream_saved_fifo=True,
            stream_zero_compute=True, reference_event_sequence_and_clocks=True,
            reference_cleanup=True),
        source_clock=clock, frames=len(arrays['note']), candidate=candidate,
        compact={key:compact_measurement(value['measurement']) for key,value in candidate.items()},
        event_counts=dict(reference_note_ons=sum(e['kind']=='on' for e in reference_events),
            candidate_note_ons=sum(e['kind']=='on' for e in candidate_events),
            reference_events=len(reference_events), candidate_events=len(candidate_events)),
        open_decoder_pitches_at_end=candidate_open,
        cleanup_emitted_ns=saved['cleanup']['emitted_ns'],
        evidence=dict(name=evidence.name, bytes=evidence.stat().st_size, sha256=digest(evidence)))


def run(spec_path, output):
    remote_only()  # Before any saved-cache, specification or output access.
    output.mkdir(parents=True, exist_ok=False)
    report_dir, logs, cache, bulk = (output/part for part in ('report','logs','cache','bulk'))
    for folder in (report_dir, logs, cache, bulk):
        folder.mkdir()
    report_path = report_dir/'report.json'
    report = dict(schema='m3_basic_pitch_onset_decoder_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), datasets={},
        installed_output_changed=False, inference_performed=False, promotion_accepted=False)
    try:
        spec = json.loads(spec_path.read_text())
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git','-C',str(root),'rev-parse','HEAD'])
        if (source != os.environ.get('SOURCE_SHA')
                or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']
                or spec['streaming_settings'] != SETTINGS
                or spec['candidate_settings'] != ONSET_DECODER
                or set(spec['datasets']) != {'ordinary','extended-middle'}):
            raise ValueError('Dispatch or frozen-scope pin mismatch')
        references = {}
        for name, pin in spec['references'].items():
            path = root/pin['path']
            check_hash(path, pin['sha256'])
            references[name] = json.loads(path.read_text())
        report['provenance'] = dict(source_commit=source, worker_commit=os.environ['GITHUB_SHA'],
            run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
            worker_repository=os.environ['GITHUB_REPOSITORY'], specification=spec,
            specification_sha256=digest(spec_path), python=sys.version, platform=platform.platform())
        report['interpretation'] = (
            'One causal decoder change on original rolling arrays, with all frames and labels retained. '
            'Primary simulated delivery reuses saved FIFO completion; zero-compute uses source arrival. '
            'No candidate worker-service, native allocation/deadline, physical latency, string assignment, '
            'unison or DAW/device acceptance measurement. No model/audio processing or threshold tuning.')
        report['stage'] = 'retrieve pinned original stream cache'
        save_json(report_path, report)
        report['artifact'] = fetch_artifact(spec['worker_repository'],
            spec['artifact'], cache/'stream', logs)
        for name, config in spec['datasets'].items():
            report['stage'] = name
            save_json(report_path, report)
            report['datasets'][name] = measure(name, config,
                references['baseline']['datasets'][name], references['stream']['datasets'][name],
                cache/'stream', bulk)
            save_json(report_path, report)
        report.update(state='completed', final=True, stage='both cached decoder comparisons complete',
                      screen=onset_screen(report['datasets']))
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_or_updated_at'] = datetime.now(timezone.utc).isoformat()
        save_json(report_path, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', dest='spec_path', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    result = run(**vars(parser.parse_args()))
    print(json.dumps(dict(state=result['state'], screen=result.get('screen'),
        datasets={name:row['compact'] for name,row in result['datasets'].items()}), allow_nan=False))
