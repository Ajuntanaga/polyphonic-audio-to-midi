"""Pinned continuous observation; three identity replays, no policy trial."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import subprocess

from tools.portable_assignment_trace import digest, verify_inputs
from tools.portable_corpus_replay import SETTINGS, command_for
from tools.portable_weak_note_residual_trace import check_identity

LEGACY_SHA = '7812dc317ee30a6b9dee9455b97f6e515492339abd912d52d7cec58f8de3d98c'
DATASETS = ('ordinary', 'extended-middle')


def run(binary, corpus, manifest, reference, output, *, dataset='ordinary'):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_unfiltered_observation_v1', dataset=dataset, final=False,
                  installed_output_changed=False, runs={})
    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    try:
        inputs = json.loads(manifest.read_text())
        ref = json.loads(reference.read_text())
        if dataset not in DATASETS or ref['dataset'] != dataset:
            raise ValueError('Reference dataset mismatch')
        required_inputs = {dataset + '.wav', dataset + '.tsv',
                           'calibration.m3cb', 'templates.tsv'}
        if set(ref['inputs']) != required_inputs:
            raise ValueError('Reference input set mismatch')
        verify_inputs(corpus, inputs, dataset)
        if ref['settings'] != SETTINGS or ref['block_samples'] != 512 or ref['reference_flags']['current-on'] != ['--diagnostic-spectral-lane-collision']:
            raise ValueError('Reference settings mismatch')
        for name, identity in ref['inputs'].items():
            if inputs['files'][name] != identity:
                raise ValueError('Input mismatch: ' + name)
        for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
            if inputs['source'][key] != ref['source'][key]:
                raise ValueError('Input provenance mismatch: ' + key)
        report.update(source=inputs['source'], binary_sha256=digest(binary),
                      reference_sha256=digest(reference), manifest_sha256=digest(manifest))
        report['historical_v4_trace_identity'] = {
            'expected_sha256': LEGACY_SHA if dataset == 'ordinary' else None,
            'state': 'pending' if dataset == 'ordinary' else 'unavailable',
        }
        base = command_for(binary.resolve(), corpus.resolve(), dataset, 'on', 512, None,
                           spectral_lane_collision=True)
        for mode in ('untraced', 'v4', 'v5'):
            stem = dataset + '-current-on-512-' + mode
            snapshot = output / (stem + '.tsv')
            midi = output / (stem + '-midi.tsv')
            trace = output / (dataset + '-current-on-512-outcome-' + mode + '.tsv')
            command = base + ['--midi-event-trace', str(midi)]
            if mode != 'untraced':
                command += ['--outcome-trace', str(trace)]
            if mode == 'v5':
                command += ['--outcome-trace-annotations']
            report['runs'][mode] = dict(command=command, state='running')
            save()
            with snapshot.open('x') as out, (output / (stem + '.stderr')).open('x') as err:
                subprocess.run(command, stdout=out, stderr=err, check=True, timeout=1200)
            check_identity(snapshot, midi, ref['runs']['current-on'])
            report['runs'][mode].update(state='passed', snapshot_sha256=digest(snapshot),
                                       midi_sha256=digest(midi), saved_identity=True)
            if mode != 'untraced':
                trace_hash = digest(trace)
                if mode == 'v4' and dataset == 'ordinary':
                    if trace_hash != LEGACY_SHA:
                        report['historical_v4_trace_identity']['state'] = 'failed'
                        raise ValueError('Legacy trace differs from run 44752010601')
                    report['historical_v4_trace_identity']['state'] = 'passed'
                report['runs'][mode]['trace_sha256'] = trace_hash
            # Retain lossless evidence in the bulk artifact, not the small report.
            for path in (snapshot, midi, *(() if mode == 'untraced' else (trace,))):
                with path.open('rb') as src, gzip.open(str(path) + '.gz', 'wb', compresslevel=3) as dst:
                    shutil.copyfileobj(src, dst)
                path.unlink()
            save()
        report.update(state='completed', final=True,
                      stage='identity passed; v5 analysis pending', promotion_accepted=False)
    except Exception as error:
        report.update(state='failed', final=True, error=str(error))
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', choices=DATASETS, default='ordinary')
    for key in ('binary', 'corpus', 'manifest', 'reference', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    run(**vars(parser.parse_args()))


if __name__ == '__main__':
    main()
