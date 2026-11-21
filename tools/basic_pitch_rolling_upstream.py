"""Frozen D2 diagnostic on a saved rolling cache; no audio or model execution.

The upstream decoder uses future context and whole-record statistics. Its indexed
intervals are measured only on the nominal rolling grid, never presented as live
delivery. Preserve D0 event, EOF and complete score identity before decoding D2.
"""
import argparse
import ast
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import statistics
from typing import List, Optional, Tuple

import numpy as np
import scipy.signal

from tools.basic_pitch_cached_diagnosis import (
    clip_labels, clip_spans, compact_measurement, decode_cached,
    frame_event_spans, indexed_note_spans, labels_from_measurement)
from tools.basic_pitch_streaming import emission_spans
from tools.pitch_detector_comparison import compare, digest, score
from tools.portable_basic_pitch_cached_diagnosis import cached_arrays, require_identity

ROOT = Path(__file__).resolve().parents[1]
CACHE = 'build/github-results/basic-pitch-streaming-44889388628/selected-evidence/ordinary-stream.npz'
STREAM = 'build/github-results/basic-pitch-streaming-44889388628/basic-pitch-streaming-result/report/report.json'
BRIDGE = 'build/github-results/basic-pitch-cached-44891340815/basic-pitch-cached-result/report/report.json'
EVENTS = 'build/github-results/basic-pitch-cached-44891340815/claude-event-evidence/files/ordinary-bridge-events.json.gz'
UPSTREAM = 'build/recovery/basic-pitch-cached-diagnosis-20261121/upstream/note_creation.py'
PINS = {
    CACHE: 'c363e9545b16b57b0f74ea756c1b80262bed12eb2b57eace189b3bfd840c548e',
    STREAM: 'a56b822b669ffa1510880d20f138819434751489a8dd74a81fe1939761ebec32',
    BRIDGE: 'da1ba0a1e2aa0bd0df9b9db07a12344d24c683a793545e60c84d2ac4a2aec773',
    EVENTS: 'acd64c3588191b8a5e14cf5928b73296df6e2b0abc9c2c70bb1723960787844d',
    UPSTREAM: '83346193f834edfc37aeadbed91a4092b574727dd2b4535e03e5ad89d2e89506',
}
SETTINGS = dict(onset_thresh=.5, frame_thresh=.3, min_note_len=11,
                infer_onsets=True, max_freq=None, min_freq=None,
                melodia_trick=True, energy_tol=11)


def load_decoder(path):
    """Compile unchanged pinned functions, without unused audio/MIDI imports.

    No replacement implementation or dependency stub is provided. The only
    librosa reference is unreachable with the frozen None frequency limits.
    A changed source or scope fails closed instead of installing dependencies.
    """
    require_identity(digest(path), PINS[UPSTREAM], 'pinned upstream decoder')
    names = {'get_infered_onsets', 'constrain_frequency', 'output_to_notes_polyphonic'}
    tree = ast.parse(path.read_text(), filename=str(path))
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in names]
    require_identity({node.name for node in selected}, names, 'upstream function set')
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = getattr(node.targets[0], 'id', None)
            if name in ('MIDI_OFFSET', 'MAX_FREQ_IDX'):
                constants[name] = ast.literal_eval(node.value)
    require_identity(constants, dict(MIDI_OFFSET=21, MAX_FREQ_IDX=87), 'upstream pitch constants')
    namespace = dict(np=np, scipy=scipy, List=List, Optional=Optional, Tuple=Tuple, **constants)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['output_to_notes_polyphonic']


def write_json(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def timed_events(events, arrays):
    times = {int(row[0]): row for row in arrays['timing']}
    result = []
    for event in events:
        timing = times[int(arrays['frames'][event['frame'], 3])]
        result.append(dict(event, available_ns=int(timing[1]), emitted_ns=int(timing[3])))
    return result


def delay_comparison(before, after, sample_rate):
    rows = []
    for a, b in zip(before['labels'], after['labels']):
        first, second = a['first_present_delay_samples'], b['first_present_delay_samples']
        rows.append(dict(label_index=a['label_index'], midi_note=a['midi_note'],
                         before_delay_samples=first, after_delay_samples=second,
                         delta_samples=second-first if first is not None and second is not None else None))
    deltas = [row['delta_samples'] for row in rows if row['delta_samples'] is not None]
    return dict(label_rows=rows, common_present_labels=len(deltas),
                paired_median_delta_samples=statistics.median(deltas) if deltas else None,
                paired_median_delta_ms=1000*statistics.median(deltas)/sample_rate if deltas else None,
                newly_present_labels=sum(r['before_delay_samples'] is None and r['after_delay_samples'] is not None for r in rows),
                newly_missing_labels=sum(r['before_delay_samples'] is not None and r['after_delay_samples'] is None for r in rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # A fresh destination prevents an accidental duplicate execution.
    args.output.mkdir(parents=True, exist_ok=False)
    for name, expected in PINS.items():
        require_identity(digest(ROOT/name), expected, name)
    stream = json.loads((ROOT/STREAM).read_text())['datasets']['ordinary']
    bridge = json.loads((ROOT/BRIDGE).read_text())['datasets']['ordinary']
    with gzip.open(ROOT/EVENTS, 'rt') as source:
        saved = json.load(source)
    arrays = cached_arrays(ROOT/CACHE, stream=True)
    d0, open_notes = decode_cached(arrays['note'], arrays['onset'])
    require_identity(d0, saved['stream_frame_events'], 'all saved D0 frame events')
    require_identity(len(d0), 1192, 'D0 event count')
    require_identity(open_notes, stream['open_decoder_pitches_at_end'], 'D0 EOF state')
    labels = labels_from_measurement(stream['measurement'])
    full_clock = dict(sample_count=10689600, sample_rate=96000)
    emission, audit = emission_spans(timed_events(d0, arrays), 'emitted_ns', full_clock['sample_count'])
    require_identity(score(emission, labels, **full_clock), stream['measurement'], 'complete full-record D0 score')
    clock = dict(sample_count=bridge['common_support']['sample_count'], sample_rate=96000)
    require_identity(clock['sample_count'], 10681922, 'common horizon')
    labels, clipping = clip_labels(labels, clock['sample_count'])
    require_identity(len(labels), 499, 'complete annotation count')
    require_identity(clipping['removed_label_samples'], 0, 'no label clipping')
    d0_spans, d0_audit = frame_event_spans(d0, 'stream', **clock)
    require_identity(score(d0_spans, labels, **clock), bridge['measurements']['C'], 'complete common D0 nominal score')
    require_identity(score(clip_spans(emission, clock['sample_count']), labels, **clock),
                     bridge['measurements']['A'], 'complete common D0 emission score')
    gates = dict(source_pins=True, d0_events=1192, eof_identity=True,
                 full_score_identity=True, common_A_identity=True, common_C_identity=True,
                 labels=499, removed_label_samples=0)
    write_json(args.output/'identity.json', gates)
    print(json.dumps(dict(identity=gates)), flush=True)

    # The pinned wrapper converts 127.7 ms this way, then rejects lengths <=11.
    require_identity(int(np.round(127.7 / 1000 * (22050 / 256))), 11, 'minimum note length')
    decode = load_decoder(ROOT/UPSTREAM)
    began = datetime.now(timezone.utc).isoformat()
    raw = decode(arrays['note'].copy(), arrays['onset'].copy(), **SETTINGS)
    indexed = []
    for left, right, note, amplitude in raw:
        if (int(left) != left or int(right) != right or int(note) != note or
                not 0 <= left < right < len(arrays['note']) or not 21 <= note <= 108 or
                not np.isfinite(amplitude)):
            raise ValueError('Invalid upstream indexed note')
        indexed.append([int(left), int(right), int(note), float(amplitude)])
    # Preserve the decode immediately, before downstream reporting can fail.
    write_json(args.output/'indexed-notes.json', dict(
        schema='m3_rolling_upstream_indexed_notes_v1', started_at=began,
        completed_at=datetime.now(timezone.utc).isoformat(), settings=SETTINGS,
        columns=['start_frame','end_frame','midi_note','amplitude'], notes=indexed,
        upstream_sha256=PINS[UPSTREAM], cache_sha256=PINS[CACHE], causal=False))
    spans = indexed_note_spans([row[:3] for row in indexed], 'stream', **clock)
    write_json(args.output/'nominal-spans.json', dict(clock=clock, spans=spans))
    measurement = score(spans, labels, **clock)
    measurements = {k:bridge['measurements'][k] for k in ('A','C','D','E')}
    measurements['D2'] = measurement
    comparisons = {}
    for before, after in (('C','D2'), ('D2','E'), ('C','E'), ('D','E')):
        comparisons[before+'_to_'+after] = compare(measurements[before], measurements[after])
    # Signed path C -> D2 -> E must equal the existing direct C -> E contrast.
    for key, delta in comparisons['C_to_E']['sample_deltas'].items():
        require_identity(comparisons['C_to_D2']['sample_deltas'][key] +
                         comparisons['D2_to_E']['sample_deltas'][key], delta, 'signed bridge '+key)
    require_identity(sum(comparisons[k]['extra_gap_pitch_samples_delta'] for k in ('C_to_D2','D2_to_E')),
                     comparisons['C_to_E']['extra_gap_pitch_samples_delta'], 'signed gap bridge')
    report = dict(schema='m3_rolling_upstream_d2_v1', created_at=datetime.now(timezone.utc).isoformat(),
        upstream_revision='fa5997af0a8210982619003269994a1be25eddf3', source_pins=PINS,
        source_run=44889388628, bridge_run=44891340815, settings=SETTINGS,
        common_clock=clock, full_record_clock=full_clock, clipping=clipping, gates=gates,
        input_frames=len(arrays['note']), indexed_notes=len(indexed), nominal_spans=len(spans),
        indexed_notes_sha256=digest(args.output/'indexed-notes.json'),
        nominal_spans_sha256=digest(args.output/'nominal-spans.json'),
        measurements=measurements, compact={k:compact_measurement(v) for k,v in measurements.items()},
        comparisons=comparisons,
        delay_comparisons={name:delay_comparison(measurements[a],measurements[b],96000)
                           for name,(a,b) in dict(C_to_D2=('C','D2'), D2_to_E=('D2','E')).items()},
        d0_audits=dict(emission=audit, nominal=d0_audit), signed_bridge_reconciles=True,
        dependency_loading='Unchanged AST functions from hash-pinned upstream; numpy/scipy only; no audio/model/MIDI imports.',
        limitations=[
            'D2 uses future frames, inferred onsets with whole-record scaling and backward Melodia traversal; no live emission clock exists here.',
            'Nominal source samples use the rolling grid, without the upstream offline timestamp correction.',
            'D2-to-E bundles rolling/offline activations and their coordinate maps; it does not isolate one cause.',
            'First-present delay is clipped to the annotation; zero can be pre-existing output, not a measured acoustic onset.',
            'Pitch occupancy merges same-pitch overlaps; strings, unison multiplicity, raw retriggers and host delivery are not measured.',
            'All 499 labels remain, including missing labels with null delay. Extra gap outputs are not missing notes.'],
        audio_opened=False, inference_performed=False, new_remote_job=False,
        installed_output_changed=False, promotion_accepted=False)
    write_json(args.output/'report.json', report)
    summary = dict(gates=gates, indexed_notes=len(indexed), compact=report['compact'],
                   comparisons={name:{k:v for k,v in value.items()
                                      if k not in ('label_deltas','label_changes','label_bands')}
                                for name,value in comparisons.items()},
                   label_counts={name:dict(
                       present_gain=sum(r['present_samples_delta'] > 0 for r in value['label_deltas']),
                       present_loss=sum(r['present_samples_delta'] < 0 for r in value['label_deltas']),
                       longest_gain=sum(r['longest_present_samples_delta'] > 0 for r in value['label_deltas']),
                       longest_loss=sum(r['longest_present_samples_delta'] < 0 for r in value['label_deltas']))
                                 for name,value in comparisons.items()},
                   delays={k:{a:b for a,b in v.items() if a!='label_rows'}
                           for k,v in report['delay_comparisons'].items()},
                   report_sha256=digest(args.output/'report.json'))
    write_json(args.output/'summary.json', summary)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
