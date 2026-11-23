"""GHA-only fixed-fixture test of two-adjacent-clean continuation tagging."""
import argparse
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess

from tools.portable_corpus_replay import timing_gates
from tools.portable_repluck_onset import (digest, verify, extract_member, compress,
                                         execute, replay_command, read_snapshot)
from tools.portable_stable_note_identity_ledger import (read_callbacks as read_ledger,
                                                       sink_spans, pitch_timeline)
from tools.portable_vst3_corpus_replay import read_callbacks as read_vst3
from tools.repluck_onset_analysis import (read_tagged, require_callback_identity,
                                         require_ledger_integrity)
from tools.stable_onset_freshness import compare_fixture, summarize, snapshot_identity


def timing_command(binary, fixture, calibration, timing_path):
    """Keep the diagnostic enabled while excluding all trace I/O from timing."""
    command = replay_command(binary, fixture, calibration, timing_path.with_suffix('.unused'))
    at = command.index('--midi-event-trace')
    del command[at:at+2]
    command[command.index('--block')+1] = '32'
    return command + ['--diagnostic-core-timing', str(timing_path)]


def run(args):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Native/audio execution is restricted to GitHub Actions')
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if actual != args.source_sha:
        raise ValueError('Source revision differs')
    spec = json.loads(args.spec.read_text())
    if spec['schema'] != 'm3_stable_onset_freshness_spec_v1':
        raise ValueError('Unknown frozen specification')
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_stable_onset_freshness_v1', state='running', final=False,
        source_sha=actual, spec_sha256=digest(args.spec), spec=spec, fixtures={},
        installed_output_changed=False, promotion_accepted=False,
        acoustic_repluck_preservation='not measured', design_data=True)

    def save():
        report['observed_at'] = datetime.now(timezone.utc).isoformat()
        (args.output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')

    save()
    try:
        report['stage'] = 'verify frozen inputs'; save()
        verify(args.manifest, spec['input_manifest_sha256'])
        calibration = args.corpus/'calibration.m3cb'
        verify(calibration, spec['calibration_sha256'])
        verify(args.report_archive, spec['reference_report']['archive_sha256'])
        verify(args.evidence_archive, spec['reference_evidence']['archive_sha256'])
        prior_path = args.output/'reference-report.json'
        extract_member(args.report_archive, 'controlled-repluck/report.json', prior_path,
                       spec['reference_report']['report_sha256'])
        prior = json.loads(prior_path.read_text())
        if (prior['state'] != 'completed' or not prior['final'] or not prior['integrity_pass']
                or prior['harness_source_sha'] != spec['reference_source_sha']):
            raise ValueError('Reference is not the pinned completed control')

        report['stage'] = 'build and native tests'; save()
        build = args.output/'native'
        execute(['cmake', '-S', 'cloud/native', '-B', str(build), '-DCMAKE_BUILD_TYPE=Release'],
                args.output/'configure.log', args.output/'configure.stderr')
        execute(['cmake', '--build', str(build), '--target', 'm3_replay', 'm3_midi_ledger_replay',
                 'm3_detector_tests', 'm3_motion_tests', '--parallel', '2'],
                args.output/'build.log', args.output/'build.stderr', timeout=900)
        execute(['ctest', '--test-dir', str(build), '--output-on-failure'],
                args.output/'tests.log', args.output/'tests.stderr', timeout=900)
        report['native_tests_pass'] = True
        binary, ledger = build/'m3_replay', build/'m3_midi_ledger_replay'
        samples, rate = spec['samples'], spec['sample_rate']
        completed = {}
        for dataset, fixture_spec in spec['datasets'].items():
            completed[dataset] = {}
            for layout, pin in fixture_spec['fixtures'].items():
                key = dataset+'/'+layout
                report['stage'] = 'fixed fixture: '+key; save()
                output = args.output/key
                output.mkdir(parents=True)
                entry = report['fixtures'][key] = dict(gates={}, runs={})
                prior_fixture = prior['fixtures'][dataset]['fixtures'][layout]
                if prior_fixture['sha256'] != pin:
                    raise ValueError('Fixture pin differs from saved report')
                fixture = output/'fixture.wav'
                extract_member(args.evidence_archive, 'fixtures/'+prior_fixture['file'], fixture, pin)
                entry['fixture_sha256'] = pin
                trace = output/'outcome.tsv'
                for mode, block, observed in (('untraced', 512, False), ('traced', 512, True),
                                               ('block32', 32, False)):
                    midi, snapshot = output/(mode+'-midi.tsv'), output/(mode+'-snapshot.tsv')
                    command = replay_command(binary, fixture, calibration, midi,
                                             trace if observed else None)
                    command[command.index('--block')+1] = str(block)
                    execute(command, snapshot, output/(mode+'.stderr'))
                    parsed = read_snapshot(snapshot, samples, rate)
                    entry['runs'][mode] = dict(command=command, snapshot=parsed,
                        snapshot_sha256=digest(snapshot), midi_sha256=digest(midi))
                for mode in ('traced', 'block32'):
                    fields = ('snapshot_sha256', 'midi_sha256') if mode == 'traced' else ('midi_sha256',)
                    for field in fields:
                        equal = entry['runs'][mode][field] == entry['runs']['untraced'][field]
                        if not equal:
                            raise ValueError(mode+' changed '+field)
                        entry['gates'][mode+'_'+field+'_identity'] = True
                snapshot = entry['runs']['untraced']['snapshot']
                if not snapshot_identity(snapshot, entry['runs']['block32']['snapshot'],
                                         left_block=512, right_block=32):
                    raise ValueError('Buffer companion changed scored snapshot fields')
                entry['gates']['block32_snapshot_fields_identity'] = True
                transitions = int(snapshot['transitions'])
                midi = output/'untraced-midi.tsv'
                events, tags, normalized_sha = read_tagged(midi, output/'normalized-midi.tsv',
                                                         samples=samples, transitions=transitions)
                entry['normalized_midi_sha256'] = normalized_sha
                references = {}
                for routing in ('per_voice', 'stable_note'):
                    ref = prior['datasets'][dataset]['runs'][layout+'-'+routing+'-32-512']
                    gz_path = output/('saved-'+routing+'.tsv.gz')
                    extract_member(args.evidence_archive, ref['trace']['file'], gz_path,
                                   ref['trace']['sha256'])
                    plain = output/('saved-'+routing+'.tsv')
                    with gzip.open(gz_path, 'rb') as source, plain.open('xb') as target:
                        shutil.copyfileobj(source, target)
                    verify(plain, ref['trace']['raw_sha256'])
                    references[routing] = read_vst3(plain, sample_count=samples,
                        expected_count=ref['native']['accepted_events'], include_events=True)['events']
                require_callback_identity(events, references['per_voice'], stable=False)
                entry['gates']['saved_per_voice_identity'] = True

                delivered, timelines, eof = {}, {}, {}
                for routing in ('per_voice', 'stable_note'):
                    callbacks_path = output/(routing+'-ledger.tsv')
                    execute([str(ledger), str(midi), str(samples), str(transitions), '512',
                             routing, str(callbacks_path)], output/(routing+'-ledger.json'),
                            output/(routing+'-ledger.stderr'))
                    native = json.loads((output/(routing+'-ledger.json')).read_text())
                    callbacks, pairs = read_ledger(callbacks_path, events, tags,
                                                  stable=routing == 'stable_note')
                    require_ledger_integrity(native, callbacks, pairs)
                    entry['gates'][routing+'_provenance_and_faults'] = True
                    spans, open_notes = sink_spans(callbacks, samples)
                    timelines[routing], eof[routing] = pitch_timeline(spans, samples), open_notes
                    delivered[routing] = callbacks
                    entry[routing+'_ledger'] = native
                    if routing == 'stable_note':
                        entry['suppressed_pairs'] = pairs
                entry['gates']['pitch_occupancy_identity'] = timelines['per_voice'] == timelines['stable_note']
                entry['gates']['open_notes_at_eof_identity'] = eof['per_voice'] == eof['stable_note']
                completed[dataset][layout] = dict(callbacks=delivered['stable_note'], references=references)

                # Timed detector run carries no event/outcome/stage/CPU trace.
                command = timing_command(binary, fixture, calibration, output/'timing.json')
                execute(command, output/'timed-snapshot.tsv', output/'timed.stderr')
                timed = read_snapshot(output/'timed-snapshot.tsv', samples, rate)
                timing = json.loads((output/'timing.json').read_text())
                entry['gates']['timed_stable_identity_enabled'] = timing.get('stable_note_identity_enabled') is True
                entry['gates']['timed_snapshot_identity'] = timed == entry['runs']['block32']['snapshot']
                entry['gates'].update(timing_gates(timing, {'output': {'fingerprint': snapshot['fingerprint']}}, 32))
                entry['timing'] = timing
                entry['timing_command'] = command
                # No audio is in the new artifacts; the original pinned fixtures remain remote.
                entry['evidence'] = [compress(p) for p in (trace, midi,
                    output/'traced-midi.tsv', output/'block32-midi.tsv', output/'normalized-midi.tsv',
                    output/'untraced-snapshot.tsv', output/'traced-snapshot.tsv',
                    output/'block32-snapshot.tsv', output/'timed-snapshot.tsv',
                    output/'per_voice-ledger.tsv', output/'stable_note-ledger.tsv')]
                save()

        report['stage'] = 'frozen response and control gates'; save()
        for dataset, fixture_spec in spec['datasets'].items():
            control = completed[dataset]['single']
            for layout, result in completed[dataset].items():
                fixture = prior['fixtures'][dataset]['fixtures'][layout]
                marker = fixture['markers'][-1]
                single = layout == 'single'
                comparison = compare_fixture(result['callbacks'], control['callbacks'],
                    result['references']['per_voice'], [] if single else control['references']['per_voice'],
                    result['references']['stable_note'], note=fixture_spec['note'], marker=marker,
                    insertion=marker-spec['pre_marker_samples'], end=marker+spec['response_after_samples'],
                    rate=rate, single=single)
                saved_response = prior['datasets'][dataset]['comparisons'][layout]['responses']['per_voice']
                if comparison['per_voice_response'] != saved_response:
                    raise ValueError('Response clock differs from the original fixed fixture screen')
                comparison['saved_stable_response'] = prior['datasets'][dataset]['comparisons'][layout]['responses']['stable_note']
                report['fixtures'][dataset+'/'+layout]['comparison'] = comparison
        report.update(summarize(report['fixtures']))
        report.update(state='completed', final=True, stage='fixed screen complete',
            decision='PASSED_FIXED_SCREEN' if report['screen_pass'] else 'REJECTED_FIXED_SCREEN',
            interpretation='Post-hoc design controls only. A pass permits a full-corpus comparison; '
                'it does not establish acoustic re-pluck preservation or live readiness. '
                'A failure closes this exact rule, without tuning.')
        save()
    except Exception as error:
        report.update(state='failed', final=True, error=repr(error), screen_pass=False)
        save()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('spec', 'corpus', 'manifest', 'report-archive', 'evidence-archive', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    run(parser.parse_args())
