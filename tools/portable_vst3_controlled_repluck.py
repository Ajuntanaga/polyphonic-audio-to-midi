"""GitHub-only fixed recorded-attack composition using a previously tested binary."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from tools.controlled_repluck import compose, response, compare_attack, prefix
from tools.portable_midi_ledger_replay import digest
from tools.portable_vst3_corpus_replay import SETTINGS, assess, read_callbacks


def extract_binary(archive, expected, destination):
    if digest(archive) != expected['archive_sha256']:
        raise ValueError('Saved binary archive hash differs')
    with zipfile.ZipFile(archive) as zipped:
        members = [name for name in zipped.namelist()
                   if name.split('/')[-1] == 'm3_vst3_corpus_replay']
        if len(members) != 1:
            raise ValueError('Saved archive does not contain one replay binary')
        with zipped.open(members[0]) as source, destination.open('xb') as target:
            shutil.copyfileobj(source, target)
    if digest(destination) != expected['sha256']:
        raise ValueError('Saved replay binary hash differs')
    destination.chmod(0o700)
    return members[0]


def make_fixtures(spec, corpus, output):
    # Imported here so local pure-contract tests never load or process audio.
    import numpy as np
    import soundfile as sf
    result = {}
    for source in spec['sources']:
        path = corpus / source['file']
        if digest(path) != source['sha256']:
            raise ValueError('Recording identity differs: ' + source['file'])
        start = source['marker'] - spec['pre_marker_samples']
        count = spec['pre_marker_samples'] + spec['post_marker_samples']
        with sf.SoundFile(path) as audio:
            if (audio.samplerate != spec['sample_rate'] or audio.channels != 1
                    or audio.frames != source['frames'] or start < 0
                    or start + count > audio.frames):
                raise ValueError('Recording clock or clip bounds differ')
            audio.seek(start)
            clip = audio.read(count, dtype='float64').tolist()
        if len(clip) != count:
            raise ValueError('Incomplete source clip')
        dataset = output / source['dataset']
        dataset.mkdir()
        row = dict(source=source, clip_start=start, clip_end=start + count, fixtures={})
        control = None
        for name, markers in spec['fixtures'].items():
            samples = compose(clip, marker_in_clip=spec['pre_marker_samples'],
                markers=markers, frames=spec['frames'], gain=spec['gain'],
                fade_frames=spec['fade_samples'])
            if name == 'single':
                control = samples
            else:
                insertion = markers[1] - spec['pre_marker_samples']
                if control is None or samples[:insertion] != control[:insertion]:
                    raise ValueError('Fixture common prefix differs')
            wav = dataset / (name + '.wav')
            sf.write(wav, np.frombuffer(samples, dtype=np.float32),
                     spec['sample_rate'], format='WAV', subtype='FLOAT')
            row['fixtures'][name] = dict(file=str(wav.relative_to(output)),
                sha256=digest(wav), peak=max(abs(x) for x in samples), markers=markers,
                common_prefix_identity=True)
        result[source['dataset']] = row
    return result


def run(args):
    captured = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True)
    if captured.strip() != args.source_sha:
        raise ValueError('Harness checkout differs')
    spec = json.loads(args.spec.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_controlled_repluck_report_v1', state='running', final=False,
        harness_source_sha=args.source_sha, spec=spec, spec_sha256=digest(args.spec),
        settings=SETTINGS, datasets={}, installed_output_changed=False,
        promotion_accepted=False, acoustic_repluck_preservation='not measured',
        external_daw_device_acceptance='not measured',
        new_timing_or_allocation_measurement=False)

    def save():
        report['observed_at'] = datetime.now(timezone.utc).isoformat()
        temporary = args.output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(args.output / 'report.json')

    save()
    try:
        if (spec['schema'] != 'm3_controlled_repluck_spec_v1'
                or digest(args.manifest) != spec['input_manifest_sha256']
                or digest(args.corpus / 'calibration.m3cb') != spec['calibration_sha256']):
            raise ValueError('Input manifest or calibration differs')
        binary = args.output / 'm3_vst3_corpus_replay'
        report['binary_member'] = extract_binary(args.binary_archive, spec['binary'], binary)
        fixtures_root = args.output / 'fixtures'
        fixtures_root.mkdir()
        report['fixtures'] = make_fixtures(spec, args.corpus, fixtures_root)
        clock = dict(sample_count=spec['frames'], sample_rate=spec['sample_rate'])
        all_integrity = []
        for source in spec['sources']:
            dataset = source['dataset']
            row = dict(runs={}, comparisons={})
            report['datasets'][dataset] = row
            events_by_case = {}
            for fixture, markers in spec['fixtures'].items():
                canonical = {}
                for bits in spec['sample_bits']:
                    for stable in (False, True):
                        mode = 'stable_note' if stable else 'per_voice'
                        for block in spec['blocks']:
                            name = f'{fixture}-{mode}-{bits}-{block}'
                            report['stage'] = dataset + '/' + name
                            save()
                            directory = args.output / dataset / name
                            directory.mkdir(parents=True)
                            trace = directory / 'callbacks.tsv'
                            wav = fixtures_root / dataset / (fixture + '.wav')
                            command = [str(binary.resolve()), '--wav', str(wav.resolve()),
                                '--calibration', str((args.corpus / 'calibration.m3cb').resolve()),
                                '--events', str(trace.resolve()), '--sample-bits', str(bits),
                                '--trial', '1', '--stable-note-identity', str(int(stable)),
                                '--block', str(block), '--batch-cell-update', '1']
                            with (directory / 'native.json').open('x') as out, (directory / 'native.stderr').open('x') as err:
                                completed = subprocess.run(command, stdout=out, stderr=err,
                                    timeout=180, check=False)
                            if completed.returncode:
                                raise RuntimeError(f'{name}: native exit {completed.returncode}; output captured')
                            native = json.loads((directory / 'native.json').read_text())
                            callbacks = read_callbacks(trace, sample_count=spec['frames'],
                                expected_count=native['accepted_events'], include_events=True)
                            events = callbacks.pop('events')
                            assessment = assess(native, callbacks, clock=clock, sample_bits=bits,
                                trial=True, stable_note_identity=stable, block_samples=block)
                            raw_sha = digest(trace)
                            identity = (raw_sha, native['detector_transitions'], native['transferred_pairs'])
                            if mode not in canonical:
                                canonical[mode] = identity
                                events_by_case[(fixture, mode)] = events
                            gates = assessment['gates']
                            gates.update(batch_execution_enabled=native.get('batch_cell_update') is True,
                                buffer_format_identity=identity == canonical[mode],
                                completion_retention_disabled=native.get('completion_midi_retention') is False)
                            if fixture != 'single':
                                insertion = markers[1] - spec['pre_marker_samples']
                                gates['control_prefix_identity'] = (prefix(events, insertion) ==
                                    prefix(events_by_case[('single', mode)], insertion))
                            assessment['gate_pass'] = all(gates.values())
                            all_integrity.append(assessment['gate_pass'])
                            compressed = trace.with_suffix('.tsv.gz')
                            with trace.open('rb') as src, compressed.open('xb') as dst:
                                with gzip.GzipFile(fileobj=dst, mode='wb', filename='', mtime=0) as archive:
                                    shutil.copyfileobj(src, archive)
                            trace.unlink()
                            row['runs'][name] = dict(native=native, callbacks=callbacks, **assessment,
                                command=command, trace=dict(file=str(compressed.relative_to(args.output)),
                                raw_sha256=raw_sha, sha256=digest(compressed)))
                            save()
            for fixture, markers in spec['fixtures'].items():
                marker = markers[-1]
                responses = {}
                for mode in ('per_voice', 'stable_note'):
                    control = [] if fixture == 'single' else events_by_case[('single', mode)]
                    responses[mode] = response(events_by_case[(fixture, mode)], control,
                        note=source['note'], marker=marker,
                        insertion=marker - spec['pre_marker_samples'],
                        end=marker + spec['response_after_marker_samples'],
                        sample_rate=spec['sample_rate'])
                row['comparisons'][fixture] = dict(responses=responses,
                    **compare_attack(responses['per_voice'], responses['stable_note']))
            save()
        comparisons = [item for row in report['datasets'].values() for item in row['comparisons'].values()]
        repeat_rows = [row['comparisons'][name] for row in report['datasets'].values()
                       for name in ('overlap', 'separated')]
        report.update(state='completed', final=True, stage='fixed comparisons complete',
            integrity_pass=all(all_integrity), run_gates_passed=sum(all_integrity),
            run_gates_total=len(all_integrity),
            baseline_response_windows=sum(item['baseline_response_observed'] for item in comparisons),
            baseline_response_windows_retained=sum(item['baseline_first_response_retained'] for item in comparisons),
            repeated_copy_baseline_responses=sum(item['baseline_response_observed'] for item in repeat_rows),
            repeated_copy_first_responses_retained=sum(item['baseline_first_response_retained'] for item in repeat_rows),
            decision='controlled waveform response only; no promotion or acoustic acceptance')
    except Exception as error:
        report.update(state='error', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('spec', 'corpus', 'manifest', 'binary-archive', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    report = run(parser.parse_args())
    print(json.dumps({key: report[key] for key in ('state', 'integrity_pass', 'decision')}))
    return 0 if report['integrity_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
