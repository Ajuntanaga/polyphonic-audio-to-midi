"""GHA-only, unchanged-core attribution of the six pinned attack fixtures."""
import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

from tools.portable_stable_note_identity_ledger import read_callbacks as read_ledger
from tools.portable_vst3_corpus_replay import read_callbacks as read_vst3
from tools.repluck_onset_analysis import (read_tagged, require_callback_identity,
    require_ledger_integrity, read_target, attribute_fixture, write_target)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(path, expected):
    actual = digest(path)
    if actual != expected:
        raise ValueError('SHA-256 differs: ' + str(path))
    return actual


def extract_member(archive, suffix, destination, expected):
    """Select one pinned member without trusting archive paths."""
    with zipfile.ZipFile(archive) as bundle:
        matches = [i for i in bundle.infolist() if not i.is_dir()
                   and (i.filename == suffix or i.filename.endswith('/' + suffix))]
        if len(matches) != 1:
            raise ValueError('Expected one archive member: ' + suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with bundle.open(matches[0]) as source, destination.open('xb') as target:
            shutil.copyfileobj(source, target)
    verify(destination, expected)
    return matches[0].filename


def compress(path):
    destination = path.with_suffix(path.suffix + '.gz')
    with path.open('rb') as source, gzip.open(destination, 'wb') as target:
        shutil.copyfileobj(source, target)
    # Only files generated in this run are removed; pinned inputs are retained.
    result = dict(file=str(destination), sha256=digest(destination), raw_sha256=digest(path))
    path.unlink()
    return result


def execute(command, stdout, stderr, *, timeout=300):
    with stdout.open('x') as out, stderr.open('x') as err:
        subprocess.run(command, stdout=out, stderr=err, check=True, timeout=timeout)


def replay_command(binary, fixture, calibration, midi, outcome=None):
    result = [str(binary), '--wav', str(fixture), '--calibration', str(calibration),
        '--a4', '440', '--input-trim', '-9', '--sensitivity', '60', '--response', '75',
        '--max-polyphony', '5', '--max-fret', '24', '--block', '512',
        '--diagnostic-spectral-lane-collision', '--diagnostic-batch-cell-update',
        '--midi-event-trace', str(midi), '--diagnostic-stable-note-identity']
    if outcome is not None:
        result += ['--outcome-trace', str(outcome)]
    return result


def read_snapshot(path, samples, rate):
    with path.open() as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    if len(rows) != 1:
        raise ValueError('Expected one complete replay snapshot')
    row = rows[0]
    if int(row['samples']) != samples or int(row['sample_rate']) != rate:
        raise ValueError('Core did not process the frozen fixture clock')
    return row


def run(args):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Native/audio execution is restricted to GitHub Actions')
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if actual != args.source_sha:
        raise ValueError('Source revision differs')
    spec = json.loads(args.spec.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_repluck_onset_v1', state='running', final=False,
        source_sha=actual, spec_sha256=digest(args.spec), spec=spec, fixtures={},
        interpretation_available=False, installed_output_changed=False,
        promotion_accepted=False, acoustic_repluck_preservation='not measured',
        new_timing_or_allocation_measurement=False)
    def save():
        report['observed_at'] = datetime.now(timezone.utc).isoformat()
        (args.output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    save()
    try:
        report['stage'] = 'verify frozen inputs and unchanged native trees'; save()
        for name, expected in spec['native_trees'].items():
            tree = subprocess.check_output(['git', 'rev-parse', 'HEAD:' + name], text=True).strip()
            if tree != expected:
                raise ValueError('Native source changed: ' + name)
        verify(args.manifest, spec['input_manifest_sha256'])
        calibration = args.corpus / 'calibration.m3cb'
        verify(calibration, spec['calibration_sha256'])
        verify(args.report_archive, spec['reference_report']['archive_sha256'])
        verify(args.evidence_archive, spec['reference_evidence']['archive_sha256'])
        prior_path = args.output / 'reference-report.json'
        extract_member(args.report_archive, 'controlled-repluck/report.json', prior_path,
                       spec['reference_report']['report_sha256'])
        prior = json.loads(prior_path.read_text())
        if (prior['state'] != 'completed' or not prior['final'] or not prior['integrity_pass']
                or prior['harness_source_sha'] != spec['reference_source_sha']):
            raise ValueError('Reference result is not the pinned completed control')

        report['stage'] = 'build unchanged replay and accepting ledger'; save()
        build = args.output / 'native'
        execute(['cmake', '-S', 'cloud/native', '-B', str(build), '-DCMAKE_BUILD_TYPE=Release'],
                args.output/'configure.log', args.output/'configure.stderr')
        execute(['cmake', '--build', str(build), '--target', 'm3_replay',
                 'm3_midi_ledger_replay', '--parallel', '2'],
                args.output/'build.log', args.output/'build.stderr', timeout=600)
        binary, ledger = build/'m3_replay', build/'m3_midi_ledger_replay'
        samples, rate = spec['samples'], spec['sample_rate']
        completed = {}
        for dataset, fixture_spec in spec['datasets'].items():
            completed[dataset] = {}
            for layout, pin in fixture_spec['fixtures'].items():
                key = dataset + '/' + layout
                report['stage'] = 'identity and observation: ' + key; save()
                output = args.output / key
                output.mkdir(parents=True)
                entry = report['fixtures'][key] = dict(gates={}, runs={})
                prior_fixture = prior['fixtures'][dataset]['fixtures'][layout]
                if prior_fixture['sha256'] != pin:
                    raise ValueError('Fixture pin differs from saved report')
                fixture = output/'fixture.wav'
                extract_member(args.evidence_archive, 'fixtures/' + prior_fixture['file'], fixture, pin)
                entry['fixture_sha256'] = pin
                trace = output/'outcome.tsv'
                for mode in ('untraced', 'traced'):
                    midi, snapshot = output/(mode+'-midi.tsv'), output/(mode+'-snapshot.tsv')
                    command = replay_command(binary, fixture, calibration, midi,
                                             trace if mode == 'traced' else None)
                    execute(command, snapshot, output/(mode+'.stderr'))
                    parsed = read_snapshot(snapshot, samples, rate)
                    entry['runs'][mode] = dict(command=command, snapshot=parsed,
                        snapshot_sha256=digest(snapshot), midi_sha256=digest(midi))
                for kind in ('snapshot_sha256', 'midi_sha256'):
                    if entry['runs']['untraced'][kind] != entry['runs']['traced'][kind]:
                        raise ValueError('Observation changed ' + kind)
                entry['gates']['traced_untraced_snapshot_identity'] = True
                entry['gates']['traced_untraced_tagged_midi_identity'] = True
                transitions = int(entry['runs']['traced']['snapshot']['transitions'])
                midi = output/'traced-midi.tsv'
                events, tags, normalized_sha = read_tagged(midi, output/'normalized-midi.tsv',
                                                         samples=samples, transitions=transitions)
                entry['normalized_midi_sha256'] = normalized_sha

                references = {}
                for routing in ('per_voice', 'stable_note'):
                    reference = prior['datasets'][dataset]['runs'][layout+'-'+routing+'-32-512']
                    gz_path = output/('saved-'+routing+'.tsv.gz')
                    extract_member(args.evidence_archive, reference['trace']['file'], gz_path,
                                   reference['trace']['sha256'])
                    plain = output/('saved-'+routing+'.tsv')
                    with gzip.open(gz_path, 'rb') as source, plain.open('xb') as target:
                        shutil.copyfileobj(source, target)
                    verify(plain, reference['trace']['raw_sha256'])
                    references[routing] = read_vst3(plain, sample_count=samples,
                        expected_count=reference['native']['accepted_events'], include_events=True)['events']
                require_callback_identity(events, references['per_voice'], stable=False)
                entry['gates']['core_per_voice_vst3_identity'] = True
                callbacks_path = output/'ledger.tsv'
                execute([str(ledger), str(midi), str(samples), str(transitions), '512',
                         'stable_note', str(callbacks_path)], output/'ledger.json', output/'ledger.stderr')
                native = json.loads((output/'ledger.json').read_text())
                callbacks, pairs = read_ledger(callbacks_path, events, tags, stable=True)
                require_ledger_integrity(native, callbacks, pairs)
                require_callback_identity(callbacks, references['stable_note'], stable=True)
                entry['gates'].update(stable_ledger_vst3_identity=True,
                    reciprocal_suppression_provenance=True, ledger_fault_free=True)
                entry['ledger'] = native
                points = read_target(trace, samples=samples, note=fixture_spec['note'])
                entry['gates']['complete_decision_grid'] = True
                entry['decisions'] = len(points)
                target_path = output/'target-candidate.jsonl.gz'
                write_target(target_path, points)
                entry['target_trace'] = dict(file=str(target_path), sha256=digest(target_path))
                completed[dataset][layout] = (points, events, tags, callbacks)
                entry['evidence'] = [compress(p) for p in (trace, midi, output/'untraced-midi.tsv',
                    output/'normalized-midi.tsv', output/'traced-snapshot.tsv',
                    output/'untraced-snapshot.tsv', callbacks_path)]
                save()

        # Interpretation starts only after every fixture passes every identity.
        report['stage'] = 'attribute saved added responses'; save()
        for dataset, fixture_spec in spec['datasets'].items():
            control = completed[dataset]['single'][0]
            for layout, (points, events, tags, callbacks) in completed[dataset].items():
                comparison = prior['datasets'][dataset]['comparisons'][layout]
                added = comparison['responses']['per_voice']['added_on_samples']
                marker = prior['fixtures'][dataset]['fixtures'][layout]['markers'][-1]
                report['fixtures'][dataset+'/'+layout]['attribution'] = attribute_fixture(
                    points, control, events, tags, callbacks, added,
                    marker=marker, note=fixture_spec['note'], sample_rate=rate)
        gates = [value for entry in report['fixtures'].values() for value in entry['gates'].values()]
        report.update(state='completed', final=True, stage='observation complete',
            integrity_pass=all(gates), gates_passed=sum(gates), gates_total=len(gates),
            interpretation_available=True,
            interpretation='Observed constructed-control onset timing only. No policy trial, '
                'acoustic preservation, installed score gain or live-host acceptance.')
        save()
    except Exception as error:
        report.update(state='failed', final=True, error=repr(error), interpretation_available=False)
        save()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('spec', 'corpus', 'manifest', 'report-archive', 'evidence-archive', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    run(parser.parse_args())
