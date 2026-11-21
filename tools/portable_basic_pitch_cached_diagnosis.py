"""One fixed saved-output bridge on GitHub CPU; no inference or audio access."""
import argparse
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

from tools.basic_pitch_cached_diagnosis import (ARMS, BRIDGES, bridge_comparisons,
    clip_labels, clip_spans, common_horizon, compact_measurement, decode_cached,
    frame_event_spans, indexed_note_spans, labels_from_measurement, offline_note_frames)
from tools.basic_pitch_streaming import SETTINGS, emission_spans
from tools.pitch_detector_comparison import compare, digest, model_spans, score
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json


def fetch_artifact(repository, config, destination, logs):
    remote_only()
    destination.mkdir()
    archive = destination/'artifact.zip'
    # Capture the binary response before interpreting it. One attempt only.
    with archive.open('xb') as output:
        process = subprocess.run(['gh', 'api',
            f'repos/{repository}/actions/artifacts/{config["id"]}/zip'],
            stdout=output, stderr=subprocess.PIPE, check=False)
    (logs/f'artifact-{config["id"]}.stderr').write_bytes(process.stderr)
    if process.returncode:
        raise RuntimeError(f'Artifact {config["id"]} download failed: exit {process.returncode}')
    check_hash(archive, config['sha256'])
    if archive.stat().st_size != config['bytes']:
        raise ValueError('Artifact byte count differs from frozen metadata')
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        for name, pin in config['files'].items():
            # upload-artifact common-root paths differ between workflows. Locate
            # each pinned basename exactly once and never extract archive paths.
            matches = [n for n in names if Path(n).name == name]
            if len(matches) != 1:
                raise ValueError('Missing or ambiguous artifact member: ' + name)
            info = bundle.getinfo(matches[0])
            if info.file_size != pin['bytes']:
                raise ValueError('Artifact member length differs: ' + name)
            target = destination/name
            with bundle.open(info) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output)
            check_hash(target, pin['sha256'])
    return dict(id=config['id'], archive_sha256=digest(archive),
                archive_bytes=archive.stat().st_size, files_verified=list(config['files']))


def require_identity(actual, expected, name):
    if actual != expected:
        raise ValueError('Saved reference identity failed: ' + name)


def cached_arrays(path, stream=False):
    import numpy as np
    with np.load(path, allow_pickle=False) as archive:
        keys = ('note', 'onset', 'frames', 'timing') if stream else ('note', 'onset')
        arrays = {key: archive[key] for key in keys}
    note, onset = arrays['note'], arrays['onset']
    if (note.ndim != 2 or not len(note) or note.shape[1] != 88 or onset.shape != note.shape
            or note.dtype != np.float32 or onset.dtype != np.float32
            or not np.isfinite(note).all() or not np.isfinite(onset).all()):
        raise ValueError('Invalid pinned activation arrays')
    if stream:
        frames, timing = arrays['frames'], arrays['timing']
        if (frames.shape != (len(note), 4) or frames.dtype != np.int64
                or timing.ndim != 2 or timing.shape[1] != 9 or timing.dtype != np.int64):
            raise ValueError('Invalid saved stream clocks')
        if (not np.array_equal(frames[:, 0], np.arange(len(note)))
                or not np.array_equal(frames[:, 1], np.arange(len(note))*256)
                or len(set(timing[:, 0].tolist())) != len(timing)):
            raise ValueError('Saved frame/source clocks are not unique')
    return arrays


def measure(name, config, baseline, offline_reference, stream_reference, cache, bulk):
    remote_only()
    clock = dict(sample_count=config['sample_count'], sample_rate=config['sample_rate'])
    if clock['sample_rate'] != SETTINGS['source_rate']:
        raise ValueError('Saved stream requires its original 96000 Hz source clock')
    labels = labels_from_measurement(baseline['measurement'])
    require_identity(score(baseline['pitch_spans'], labels, **clock),
                     baseline['measurement'], name + ' CURRENT occupancy')
    rolling = cached_arrays(cache/'stream'/(name+'-stream.npz'), stream=True)
    offline = cached_arrays(cache/'offline'/(name+'-activations.npz'))
    event_doc = json.loads((cache/'stream'/(name+'-events.json')).read_text())
    notes = json.loads((cache/'offline'/(name+'-notes.json')).read_text())['events']
    require_identity(event_doc['frame_columns'],
        ['frame', 'nominal_model_sample', 'window_end_exclusive', 'arrived_source_samples'], 'frame columns')
    require_identity(event_doc['timing_columns'],
        ['source_end', 'arrival_ns', 'service_ns', 'finish_ns', 'queued_ns',
         'resample_and_buffer_ns', 'model_ns', 'decode_ns', 'model_called'], 'timing columns')
    stream_events, stream_open = decode_cached(rolling['note'], rolling['onset'])
    require_identity(stream_open, event_doc['cleanup']['notes'], 'decoder EOF state')
    clocks = {int(row[0]): row for row in rolling['timing']}
    reconstructed = []
    for event in stream_events:
        frame = rolling['frames'][event['frame']]
        timing = clocks[int(frame[3])]
        reconstructed.append(dict(event, available_ns=int(timing[1]), emitted_ns=int(timing[3])))
    require_identity(reconstructed, event_doc['events'], 'rolling decoded events and delivery clocks')
    saved_events = event_doc['events']
    spans_a, audit_a = emission_spans(saved_events, 'emitted_ns', clock['sample_count'])
    spans_b, audit_b = emission_spans(saved_events, 'available_ns', clock['sample_count'])
    spans_f, audit_f = model_spans(notes, **clock)
    for arm, spans, expected in (
            ('A', spans_a, stream_reference['measurement']),
            ('B', spans_b, stream_reference['zero_compute_measurement']),
            ('F', spans_f, offline_reference)):
        require_identity(score(spans, labels, **clock), expected, name + ' full-record arm ' + arm)
    indexed, inverse_audit = offline_note_frames(notes, len(offline['note']))
    offline_events, offline_open = decode_cached(offline['note'], offline['onset'])
    horizon = common_horizon(clock['sample_count'], len(rolling['note']),
                             len(offline['note']), clock['sample_rate'])
    common_labels, clipping = clip_labels(labels, horizon)
    common_clock = dict(sample_count=horizon, sample_rate=clock['sample_rate'])
    spans_c, audit_c = frame_event_spans(stream_events, 'stream', **common_clock)
    spans_d, audit_d = frame_event_spans(offline_events, 'offline_window', **common_clock)
    spans_e = indexed_note_spans(indexed, 'offline_window', **common_clock)
    spans = dict(A=clip_spans(spans_a, horizon), B=clip_spans(spans_b, horizon),
                 C=spans_c, D=spans_d, E=spans_e, F=clip_spans(spans_f, horizon))
    measurements = {arm: score(value, common_labels, **common_clock) for arm, value in spans.items()}
    current = score(clip_spans(baseline['pitch_spans'], horizon), common_labels, **common_clock)
    bridges = bridge_comparisons(measurements)
    evidence = bulk/(name+'-bridge-events.json.gz')
    with gzip.open(evidence, 'wt', encoding='utf-8') as output:
        json.dump(dict(stream_frame_events=stream_events, offline_forward_events=offline_events,
                       offline_indexed_notes=indexed, common_horizon=horizon,
                       original_label_indices=clipping['original_label_indices'], arm_spans=spans),
                  output, allow_nan=False, separators=(',', ':'))
    return dict(full_record_identity=dict(current=True, A=True, B=True, F=True,
                    stream_event_sequence_and_clocks=True, stream_cleanup_state=True),
        cache_frames=dict(stream=len(rolling['note']), offline=len(offline['note'])),
        common_support=dict(**common_clock, recording_sample_count=clock['sample_count'],
                            removed_source_samples=clock['sample_count']-horizon, **clipping),
        endpoint_inversion=inverse_audit,
        event_audits=dict(A=audit_a, B=audit_b, C=audit_c, D=audit_d, F=audit_f,
                          offline_forward_open_pitches=offline_open),
        measurements=measurements, current_measurement=current,
        compact={arm: compact_measurement(value) for arm, value in measurements.items()},
        bridges=bridges,
        comparisons_to_current={arm: compare(current, value) for arm, value in measurements.items()},
        evidence=dict(name=evidence.name, bytes=evidence.stat().st_size, sha256=digest(evidence)))


def run(spec_path, output):
    remote_only()  # Must precede all recorded-cache file access and downloads.
    output.mkdir(parents=True, exist_ok=False)
    report_dir, logs, cache, bulk = (output/part for part in ('report', 'logs', 'cache', 'bulk'))
    for folder in (report_dir, logs, cache, bulk):
        folder.mkdir()
    report_path = report_dir/'report.json'
    report = dict(schema='m3_basic_pitch_cached_diagnosis_v1', state='running', final=False,
                  started_at=datetime.now(timezone.utc).isoformat(), datasets={},
                  installed_output_changed=False, inference_performed=False, promotion_accepted=False)
    try:
        spec = json.loads(spec_path.read_text())
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git', '-C', str(root), 'rev-parse', 'HEAD'])
        if (source != os.environ.get('SOURCE_SHA')
                or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']
                or spec['streaming_settings'] != SETTINGS
                or set(spec['datasets']) != {'ordinary', 'extended-middle'}):
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
        report['arms'] = ARMS
        report['interpretation'] = (
            'Signed, path-dependent bridges on a common horizon; not independent causal loss shares. '
            'C/D/E use nominal model coordinates, not deliverable MIDI timestamps or measured acoustic onset. '
            'D-C bundles resampling, context, windowing and selected readout; other model frames were not saved. '
            'E-D bundles upstream noncausal decoding and forward decoding. F-E changes timestamp convention only. '
            'Historical A/B/F scores must match exactly before common-horizon comparisons. No fitted shifts, '
            'threshold tuning, new inference, string assignment, realtime deadline or live-host claim.')
        report['artifacts'] = {}
        for name, config in spec['artifacts'].items():
            report['stage'] = 'retrieve pinned ' + name + ' cache'
            save_json(report_path, report)
            report['artifacts'][name] = fetch_artifact(spec['worker_repository'], config, cache/name, logs)
        for name, config in spec['datasets'].items():
            report['stage'] = name
            save_json(report_path, report)
            report['datasets'][name] = measure(name, config, references['baseline']['datasets'][name],
                references['offline']['datasets'][name], references['stream']['datasets'][name], cache, bulk)
            save_json(report_path, report)
        report.update(state='completed', final=True, stage='both cached comparisons complete')
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
    print(json.dumps(dict(state=result['state'],
        datasets={name: row['compact'] for name, row in result['datasets'].items()}), allow_nan=False))
