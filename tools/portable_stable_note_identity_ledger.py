"""Bounded ordinary-waveform screen of diagnostic stable MIDI note identity.

Physical assignment remains detector metadata. Sink voice IDs in stable mode
are note identities, never string labels. Run native programs only on GHA.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from tools.frozen_cue_corpus_gate import read_replay
from tools.midi_lifecycle_analysis import EVENT_FIELDS, read_events, summarize
from tools.portable_assignment_trace import compress_trace_window, digest, verify_inputs
from tools.portable_corpus_replay import SETTINGS, command_for
from tools.portable_midi_lane_trace import HELD_LABEL
from tools.portable_routing_trace import outcome_window

FLAG = '--diagnostic-stable-note-identity'
COLLISION = '--diagnostic-spectral-lane-collision'
CALLBACK_FIELDS = ('sample', 'phase', 'kind', 'note', 'velocity', 'voice_id',
                   'channel', 'source_sequence')


def read_tags(path, current):
    """Require exact original event bytes after removing only the new field."""
    checksum = hashlib.sha256(b'# m3_midi_events_v1\n' +
                              ('\t'.join(EVENT_FIELDS) + '\n').encode())
    tags = {}
    with path.open() as stream:
        if stream.readline() != '# m3_midi_events_v2\n':
            raise ValueError('Unknown tagged event schema')
        if stream.readline() != '\t'.join((*EVENT_FIELDS, 'continuation_voice_id')) + '\n':
            raise ValueError('Invalid tagged event header')
        count = 0
        for count, line in enumerate(stream, 1):
            fields = line.rstrip('\n').split('\t')
            if len(fields) != 7 or not fields[6].isascii() or not fields[6].isdigit():
                raise ValueError('Malformed continuation tag')
            tag = int(fields[6])
            if tag not in (*range(8), 255) or count > len(current):
                raise ValueError('Invalid continuation identity/count')
            expected = current[count - 1]
            if fields[:6] != [str(expected[key]) for key in EVENT_FIELDS]:
                raise ValueError('Tagged diagnostic changed a source event')
            checksum.update(('\t'.join(fields[:6]) + '\n').encode())
            tags[expected['sequence']] = tag
    if count != len(current):
        raise ValueError('Incomplete tagged capture')
    return tags, checksum.hexdigest()


def read_callbacks(path, events, tags, *, stable):
    source = {event['sequence']: event for event in events}
    callbacks, seen = [], set()
    with path.open() as stream:
        if stream.readline().rstrip('\n') != '# m3_ledger_callbacks_v1':
            raise ValueError('Unknown callback schema')
        rows = csv.DictReader(stream, delimiter='\t')
        if rows.fieldnames != list(CALLBACK_FIELDS):
            raise ValueError('Invalid callback header')
        for row in rows:
            if set(row) != set(CALLBACK_FIELDS) or row['phase'] != 'source':
                raise ValueError('Unexpected cleanup or malformed callback')
            for key in CALLBACK_FIELDS:
                if key not in ('kind', 'phase'):
                    if not row[key] or not row[key].isascii() or not row[key].isdigit():
                        raise ValueError('Invalid callback integer')
                    row[key] = int(row[key])
            sequence = row['source_sequence']
            if sequence not in source or sequence in seen:
                raise ValueError('Unknown or duplicated source callback')
            event = source[sequence]
            if any(row[key] != event[key] for key in ('sample', 'kind', 'note', 'velocity')):
                raise ValueError('Callback changed source payload')
            if not 0 <= row['voice_id'] < 8 or not 1 <= row['channel'] <= 8:
                raise ValueError('Invalid sink identity/channel')
            if not stable and (row['voice_id'] != event['voice_id'] or
                               row['channel'] != event['voice_id'] + 1):
                raise ValueError('Physical routing changed')
            if callbacks and row['sample'] < callbacks[-1]['sample']:
                raise ValueError('Callbacks reordered across samples')
            seen.add(sequence)
            callbacks.append(row)
    missing = set(source) - seen
    if not stable and missing:
        raise ValueError('Default ledger dropped a source event')
    # A dropped event must belong to one explicit, reciprocal same-sample
    # source pair. An untagged repluck, a retune or one side alone cannot pass.
    remaining = set(missing)
    while remaining:
        sequence = min(remaining)
        event = source[sequence]
        partner = [other for other in remaining if other != sequence and
            source[other]['sample'] == event['sample'] and
            source[other]['note'] == event['note'] and
            source[other]['kind'] != event['kind'] and
            source[other]['voice_id'] == tags[sequence] and
            tags[other] == event['voice_id'] and
            source[other]['voice_id'] != event['voice_id']]
        if len(partner) != 1:
            raise ValueError('Suppressed callback lacks unique reciprocal provenance')
        remaining.difference_update((sequence, partner[0]))
    return callbacks, len(missing) // 2


def sink_spans(callbacks, samples):
    active, spans = {}, []
    for event in callbacks:
        identity = event['voice_id']
        if event['kind'] == 'on':
            if identity in active or event['velocity'] == 0:
                raise ValueError('Duplicate sink identity or silent attack')
            active[identity] = event
        elif event['kind'] == 'off':
            old = active.pop(identity, None)
            if old is None or any(old[key] != event[key] for key in ('note', 'channel')):
                raise ValueError('Sink release does not match its attack')
            spans.append((old['sample'], event['sample'], old['note']))
        else:
            raise ValueError('Invalid callback kind')
    spans.extend((event['sample'], samples, event['note']) for event in active.values())
    return sorted(spans), sorted(event['note'] for event in active.values())


def pitch_timeline(spans, samples):
    """Canonical positive-duration pitch multiplicity, including all gaps."""
    edges = defaultdict(Counter)
    edges[0]; edges[samples]
    for left, right, note in spans:
        if not 0 <= left <= right <= samples:
            raise ValueError('Sink span outside recording')
        edges[left][note] += 1
        edges[right][note] -= 1
    active, timeline, previous = Counter(), [], 0
    for sample in sorted(edges):
        state = tuple(sorted((note, count) for note, count in active.items() if count))
        if sample > previous:
            if timeline and timeline[-1][2] == state:
                timeline[-1] = (timeline[-1][0], sample, state)
            else:
                timeline.append((previous, sample, state))
        active.update(edges[sample])
        if any(value < 0 for value in active.values()):
            raise ValueError('Negative pitch multiplicity')
        previous = sample
    if any(active.values()):
        raise ValueError('Unclosed measured span')
    return timeline


def label_metrics(spans, callbacks, labels):
    results = []
    for label in labels:
        left, right, note = label['start_sample'], label['end_sample'], label['midi_note']
        overlaps = sorted((max(start, left), min(end, right)) for start, end, pitch in spans
                          if pitch == note and start < right and end > left)
        covered = 0
        end = left
        for start, stop in overlaps:
            covered += max(0, stop - max(start, end))
            end = max(end, stop)
        results.append(dict(label_index=label['label_index'], midi_note=note,
            label_samples=right - left, pitch_present_samples=covered,
            longest_sink_hold_samples=max((stop - start for start, stop in overlaps), default=0),
            note_ons_inside_label=sum(event['kind'] == 'on' and event['note'] == note and
                left <= event['sample'] < right for event in callbacks)))
    return results


def pitch_safety(timeline, callbacks, labels):
    edges = defaultdict(Counter)
    for label in labels:
        edges[label['start_sample']][label['midi_note']] += 1
        edges[label['end_sample']][label['midi_note']] -= 1
    counts = dict(false_wrong_note_voice_samples=0, false_gap_voice_samples=0,
                  false_wrong_note_onsets=0, false_gap_onsets=0)
    expected, index = Counter(), 0
    boundaries = sorted(edges)
    for left, right, state in timeline:
        cuts = [left] + [point for point in boundaries if left < point < right] + [right]
        for start, stop in zip(cuts, cuts[1:]):
            while index < len(boundaries) and boundaries[index] <= start:
                expected.update(edges[boundaries[index]])
                index += 1
            for note, voices in state:
                key = ('false_gap_voice_samples' if not any(expected.values()) else
                       'false_wrong_note_voice_samples' if not expected[note] else None)
                if key:
                    counts[key] += (stop - start) * voices
    expected, index = Counter(), 0
    for event in callbacks:
        while index < len(boundaries) and boundaries[index] <= event['sample']:
            expected.update(edges[boundaries[index]])
            index += 1
        if event['kind'] == 'on':
            if not any(expected.values()):
                counts['false_gap_onsets'] += 1
            elif not expected[event['note']]:
                counts['false_wrong_note_onsets'] += 1
    return counts


def run(binary, ledger_binary, corpus, manifest_path, reference_path, output, timeout=900):
    output.mkdir(parents=True, exist_ok=False)
    binary, ledger_binary, corpus = binary.resolve(), ledger_binary.resolve(), corpus.resolve()
    report = dict(schema='m3_stable_note_identity_ledger_v1', state='running', final=False,
        dataset='ordinary', settings=SETTINGS, target_label=HELD_LABEL, runs={}, ledgers={},
        installed_output_changed=False, promotion_accepted=False,
        native_timing='not measured', corpus_allocations='not measured',
        buffer_partitioning='not measured', host_delivery_verified=False,
        interpretation='Stable sink IDs are independent of inferred strings. This accepting '
            'file sink is not a VST3 host; physical-string held scores remain detector measurements.',
        articulation_guard='Continuation requires continuous selection, a single unchanged-pitch '
            'owner, no pending attack and available causal onset evidence with no energy rise. '
            'Missing or rising evidence retains the original Off/On. This guard does not '
            'establish acoustic re-pluck detection quality.')

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        path = output / 'report.json.tmp'
        path.write_text(json.dumps(report, indent=2) + '\n')
        path.replace(output / 'report.json')

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        reference = json.loads(reference_path.read_text())
        verify_inputs(corpus, manifest, 'ordinary')
        for name, item in reference['inputs'].items():
            if digest(corpus / name) != item['sha256']:
                raise ValueError('Frozen input changed: ' + name)
        report.update(source=manifest.get('source'), binary_sha256=digest(binary),
            ledger_binary_sha256=digest(ledger_binary), reference_sha256=digest(reference_path))
        current_events, parsed_current, tags = None, None, None
        for stem, flags in (('reference-off', ()), ('current-on', (COLLISION,)),
                            ('tagged-on', (COLLISION, FLAG))):
            report['stage'] = stem
            save()
            destination = output / stem
            destination.mkdir()
            midi, outcome, replay = (destination / name for name in
                                    ('midi-event.tsv', 'outcome.tsv', 'replay.tsv'))
            command = command_for(binary, corpus, 'ordinary', 'off', 512, None)
            command.extend((*flags, '--midi-event-trace', str(midi), '--outcome-trace', str(outcome)))
            with replay.open('x') as stdout, (destination / 'replay.stderr').open('x') as stderr:
                subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=timeout)
            parsed = read_replay(replay)
            with replay.open() as stream:
                aggregate = next(csv.DictReader(stream, delimiter='\t'))
            samples, rate, transitions = (int(aggregate[key]) for key in
                                         ('samples', 'sample_rate', 'transitions'))
            saved = reference['runs']['current-on' if stem == 'tagged-on' else stem]
            if samples != saved['sample_count'] or rate != saved['sample_rate']:
                raise ValueError('Frozen recording clock changed')
            result = dict(tsv_sha256=digest(replay), midi_sha256=digest(midi),
                outcome_sha256=digest(outcome), sample_count=samples, sample_rate=rate,
                transitions=transitions, output=parsed['output'])
            report['runs'][stem] = result
            if stem == 'tagged-on':
                tags, normalized = read_tags(midi, current_events)
                if transitions != len(current_events) or normalized != saved['midi_trace_sha256']:
                    raise ValueError('Tagging changed normalized MIDI capture')
                result['normalized_midi_sha256'] = normalized
                result['tagged_events'] = sum(value != 255 for value in tags.values())
            else:
                events = read_events(midi, sample_count=samples, transition_count=transitions)
                if result['midi_sha256'] != saved['midi_trace_sha256']:
                    raise ValueError(stem + ' raw MIDI reference changed')
                if stem == 'current-on':
                    current_events, parsed_current = events, parsed
                    lifecycle = summarize(events, parsed['labels'], sample_count=samples,
                                          sample_rate=rate, include_output_safety=True)
                    if not lifecycle['coverage_valid']:
                        raise ValueError('Current physical lifecycle invalid')
                    result['physical_lifecycle'] = lifecycle
                    result['target_physical_hold'] = next(row for row in lifecycle['labels']
                        if row['label_index'] == HELD_LABEL['label_index'])
            if result['tsv_sha256'] != saved['tsv_sha256'] or result['output'] != saved['output']:
                raise ValueError(stem + ' scored output changed')
            if stem != 'reference-off' and result['outcome_sha256'] != reference['current_outcome_sha256']:
                raise ValueError('Tagging/current physical inference changed')
            result['saved_reference_identical'] = True
            outcome_window(outcome, samples, 0, 0)
            result['outcome'] = compress_trace_window(outcome, start=0, end=samples)
            outcome.unlink()
            if stem != 'tagged-on':
                result['midi'] = compress_trace_window(midi, start=0, end=samples)
                midi.unlink()
            save()

        target = next(row for row in parsed_current['labels']
                      if row['label_index'] == HELD_LABEL['label_index'])
        if any(target[key] != value for key, value in HELD_LABEL.items()):
            raise ValueError('Target annotation changed')
        midi = output / 'tagged-on/midi-event.tsv'
        timelines = {}
        for routing in ('per_voice', 'stable_note'):
            report['stage'] = routing + ' ledger'
            save()
            callbacks_path = output / (routing + '-callbacks.tsv')
            command = [str(ledger_binary), str(midi), str(samples), str(transitions),
                       '512', routing, str(callbacks_path)]
            result_path = output / (routing + '-native.json')
            with result_path.open('x') as stdout, (output / (routing + '.stderr')).open('x') as stderr:
                subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=90)
            native = json.loads(result_path.read_text())
            callbacks, suppressed = read_callbacks(callbacks_path, current_events, tags,
                                                   stable=routing == 'stable_note')
            spans, opens = sink_spans(callbacks, samples)
            timeline = timelines[routing] = pitch_timeline(spans, samples)
            faults = ('queue_rejected_events', 'unqueued_after_failure', 'cleanup_callbacks',
                      'blocked_blocks', 'detection_disabled_blocks', 'callback_pairing_errors')
            if any(native[key] != 0 for key in faults) or native['output_blocked_at_eof'] or native['cleanup_pending_at_eof']:
                raise ValueError('Ledger delivery or pairing failure')
            if (native['source_callbacks'] != len(callbacks) or
                    native['transferred_pairs'] != suppressed or
                    native['suppressed_source_events'] != 2 * suppressed):
                raise ValueError('Native counts disagree with source provenance')
            labels = label_metrics(spans, callbacks, parsed_current['labels'])
            report['ledgers'][routing] = dict(native=native, open_pitches_at_eof=opens,
                labels=labels, target=next(row for row in labels if row['label_index'] == 17),
                pitch_safety=pitch_safety(timeline, callbacks, parsed_current['labels']),
                callbacks=compress_trace_window(callbacks_path, start=0, end=samples))
            callbacks_path.unlink()
            save()
        report['runs']['tagged-on']['midi'] = compress_trace_window(midi, start=0, end=samples)
        midi.unlink()
        before, after = (report['ledgers'][key] for key in ('per_voice', 'stable_note'))
        losses = [new['label_index'] for old, new in zip(before['labels'], after['labels'])
            if new['pitch_present_samples'] < old['pitch_present_samples'] or
               new['longest_sink_hold_samples'] < old['longest_sink_hold_samples'] or
               new['note_ons_inside_label'] > old['note_ons_inside_label']]
        safety_delta = {key: after['pitch_safety'][key] - before['pitch_safety'][key]
                        for key in before['pitch_safety']}
        improved = (after['target']['longest_sink_hold_samples'] > before['target']['longest_sink_hold_samples'] and
                    after['target']['note_ons_inside_label'] < before['target']['note_ons_inside_label'])
        identical = timelines['per_voice'] == timelines['stable_note']
        passed = identical and not losses and improved and all(value <= 0 for value in safety_delta.values())
        report.update(state='completed', final=True, stage='bounded accepting-sink screen complete',
            pitch_multiplicity_timeline_identical=identical, label_regressions=losses,
            pitch_safety_delta=safety_delta, target_improved=improved,
            bounded_screen_pass=passed, decision='eligible for wider validation' if passed else 'rejected',
            physical_string_inference_and_held_scores='bit-identical to current detector; sink IDs are not strings')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'ledger-binary', 'corpus', 'manifest', 'reference-report', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    run(args.binary, args.ledger_binary, args.corpus, args.manifest, args.reference_report, args.output)


if __name__ == '__main__':
    main()
