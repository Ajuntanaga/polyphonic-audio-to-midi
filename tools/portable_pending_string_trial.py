"""Compare pending string reservation with both saved ordinary output policies.

Run on an offloaded worker. Tuner label matches and raw emitted-note durations
are separate measurements; neither promotes a trial into the installed plugin.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from tools.frozen_cue_corpus_gate import compare_replays, read_replay
from tools.midi_lifecycle_analysis import CONFLICT_FIELDS, raw_conflicts, read_events, summarize
from tools.portable_assignment_trace import compress_trace_window, digest, verify_inputs
from tools.portable_corpus_replay import SETTINGS, command_for
from tools.portable_midi_lane_trace import HELD_LABEL
from tools.portable_retained_spectral_trial import COLLISION_FLAG


FLAG = '--diagnostic-pending-string-reservation'
# Measured in github-held-note-costs-20261110.json, before this runtime change.
HELD_BASELINE = dict(exact_held_samples=40000, note_ons_inside_label=156)
CONDITIONS = (('reference-off', ()), ('current-on', (COLLISION_FLAG,)),
              ('trial-on', (COLLISION_FLAG, FLAG)))


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    report = dict(schema='m3_pending_string_reservation_trial_v1', state='running',
        final=False, stage='verify inputs', dataset='ordinary', settings=SETTINGS,
        runs={}, target_label=HELD_LABEL, held_baseline=HELD_BASELINE,
        diagnostic_flag=FLAG, installed_output_changed=False, promotion_accepted=False,
        native_timing='not measured', live_readiness='not measured',
        policy='Selected immature singleton candidates retain their assignment evidence '
            'and preview a string without occupying it in the sounding-note assignment. '
            'Ready attacks, atomic handoffs, existing owners and group evidence use '
            'the ordinary solve. Independent MIDI ownership remains enabled.')

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        references = json.loads(reference_path.read_text())['runs']
        verify_inputs(corpus, manifest, 'ordinary')
        report.update(source=manifest.get('source', {}), binary_sha256=digest(binary),
            input_manifest_sha256=digest(manifest_path), reference_report_sha256=digest(reference_path))
        parsed_runs = {}
        for stem, flags in CONDITIONS:
            destination = output / stem
            destination.mkdir()
            midi_path = destination / 'midi-event.tsv'
            command = command_for(binary, corpus, 'ordinary', 'off', 512, None)
            command.extend((*flags, '--midi-event-trace', str(midi_path)))
            report.update(stage=stem, command=command)
            save()
            replay_path = destination / 'replay.tsv'
            started = time.monotonic()
            with replay_path.open('x') as stdout, (destination / 'replay.stderr').open('x') as stderr:
                subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=timeout)
            parsed = parsed_runs[stem] = read_replay(replay_path)
            with replay_path.open() as stream:
                aggregate = next(csv.DictReader(stream, delimiter='\t'))
            samples, rate = int(aggregate['samples']), int(aggregate['sample_rate'])
            if rate != 96000 or not 0 <= HELD_LABEL['start_sample'] < HELD_LABEL['end_sample'] <= samples:
                raise ValueError('Recorded held label or sample clock changed')
            if stem != 'reference-off' and samples != report['runs']['reference-off']['sample_count']:
                raise ValueError('Trial recording length differs from OFF')
            target = [row for row in parsed['labels'] if all(
                row[key] == value for key, value in HELD_LABEL.items())]
            if len(target) != 1:
                raise ValueError('Recorded held label identity changed')
            events = read_events(midi_path, sample_count=samples,
                                 transition_count=int(aggregate['transitions']))
            result = dict(elapsed_seconds=time.monotonic() - started,
                tsv_sha256=digest(replay_path), output=parsed['output'],
                exact_matches_by_string_count=parsed['exact_matches_by_string_count'],
                sample_rate=rate, sample_count=samples, raw_midi=raw_conflicts(events),
                midi_sha256=digest(midi_path), lifecycle=summarize(events, parsed['labels'],
                    sample_count=samples, sample_rate=rate))
            report['runs'][stem] = result
            if stem != 'trial-on':
                reference = references['reference-off' if stem == 'reference-off' else 'trial-on']
                identity = (result['tsv_sha256'] == reference['tsv_sha256']
                    and result['output'] == reference['output']
                    and result['midi_sha256'] == reference['traces']['midi-event']['raw_sha256'])
                result['saved_reference_bit_identical'] = identity
                if not identity:
                    raise ValueError(stem + ' differs from its saved snapshot or raw MIDI reference')
            if result['lifecycle']['coverage_valid']:
                result['held_label'] = next(row for row in result['lifecycle']['labels']
                    if row['label_index'] == HELD_LABEL['label_index'])
            if stem == 'current-on' and (not result['lifecycle']['coverage_valid'] or any(
                    result['held_label'][key] != value for key, value in HELD_BASELINE.items())):
                raise ValueError('Current ON held-note measurement differs from its saved baseline')
            result['traces'] = {'midi-event': compress_trace_window(midi_path, start=0, end=samples)}
            result['traces']['midi-event']['scope'] = 'complete recording'
            midi_path.unlink()
            save()

        current, trial = (report['runs'][stem] for stem in ('current-on', 'trial-on'))
        comparisons = {stem: compare_replays(parsed_runs[stem], parsed_runs['trial-on'])
                       for stem in ('reference-off', 'current-on')}
        midi_delta = {stem: {key: trial['raw_midi']['counts'][key] -
            report['runs'][stem]['raw_midi']['counts'][key] for key in CONFLICT_FIELDS}
            for stem in ('reference-off', 'current-on')}
        midi_safe = all(value <= 0 for delta in midi_delta.values() for value in delta.values())
        valid = trial['lifecycle']['coverage_valid']
        held_losses = None
        improvement = False
        if valid:
            held_losses = [dict(label_index=before['label_index'],
                before=before['exact_held_samples'], after=after['exact_held_samples'])
                for before, after in zip(current['lifecycle']['labels'], trial['lifecycle']['labels'])
                if after['exact_held_samples'] < before['exact_held_samples']]
            improvement = (trial['held_label']['exact_held_samples'] > HELD_BASELINE['exact_held_samples']
                and trial['held_label']['note_ons_inside_label'] < HELD_BASELINE['note_ons_inside_label'])
        passed = (all(value['gate_pass'] for value in comparisons.values()) and midi_safe
                  and valid and not held_losses and improvement)
        report.update(state='completed', final=True, stage='offline screen collected',
            comparisons=comparisons, raw_midi_delta=midi_delta, raw_midi_no_regression=midi_safe,
            held_label_improved=improvement, held_sample_losses=held_losses,
            full_recording_screen_pass=passed,
            decision='eligible for wider validation' if passed else 'rejected',
            interpretation='Require no passage snapshot loss or increased false-output '
                'count against both OFF and current ON, no raw-event regression, valid '
                'pairing, no passage held-sample loss against current ON, and more exact '
                'held samples with fewer attacks in the target label. Held samples are '
                'raw MIDI durations, not labeled-frame matches or host delivery. '
                'Cross-corpus, buffer, allocation, timing and host gates remain open.')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference-report', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--replay-timeout-seconds', type=int, default=900)
    args = parser.parse_args()
    if args.replay_timeout_seconds <= 0:
        parser.error('--replay-timeout-seconds must be positive')
    run(args.binary, args.corpus, args.manifest, args.reference_report, args.output,
        timeout=args.replay_timeout_seconds)


if __name__ == '__main__':
    main()
