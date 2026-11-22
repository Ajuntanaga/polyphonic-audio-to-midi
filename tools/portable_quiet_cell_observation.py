"""Pinned CURRENT replays with a const raw-cell sidecar, observation only."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import shutil
import subprocess

from tools.portable_assignment_trace import digest, verify_inputs
from tools.portable_corpus_replay import SETTINGS, command_for
from tools.portable_weak_note_residual_trace import check_identity

DATASETS = ('ordinary', 'extended-middle')
MODES = ('untraced', 'v5', 'cells')
FLAGS = ['--diagnostic-spectral-lane-collision']
V5_HEADER = ('sample tick quiet signal_samples labels matched_labels voices '
             'candidates input_power floor_stats').split()
CELL_HEADER = ('sample tick quiet note available input_power decay').split() + [
    f'h{h}_{field}' for h in range(1, 7) for field in ('hz', 'real', 'imag')]


def validate_sidecar(trace, cells):
    """Stream one-to-one coverage and numeric integrity; never score a policy."""
    counts = defaultdict(lambda: dict(ticks=0, rows=0, available=0, nonzero_cells=0))
    frames = total = 0
    with trace.open() as legacy, cells.open() as raw:
        if legacy.readline().strip() != '# m3_candidate_outcome_v5' or \
                legacy.readline().rstrip('\n').split('\t') != V5_HEADER:
            raise ValueError('Unexpected v5 header')
        if raw.readline().strip() != '# m3_outcome_cells_v1' or \
                raw.readline().rstrip('\n').split('\t') != CELL_HEADER:
            raise ValueError('Unexpected cell header')
        for line in legacy:
            fields = line.rstrip('\n').split('\t')
            if len(fields) != 10:
                raise ValueError('Malformed v5 row')
            frames += 1
            quiet = fields[2]
            counts[quiet]['ticks'] += 1
            power = float(fields[8])
            if not math.isfinite(power) or power < 0:
                raise ValueError('Invalid v5 input power')
            for candidate in fields[7].split(',') if fields[7] else ():
                values = candidate.split(':')
                if len(values) != 46:
                    raise ValueError('Candidate tuple changed')
                row = raw.readline().rstrip('\n').split('\t')
                if len(row) != 25 or row[:4] != fields[:3] + [values[0]]:
                    raise ValueError('Cell row coverage/order mismatch')
                if row[4] not in ('0', '1'):
                    raise ValueError('Invalid availability flag')
                numbers = list(map(float, row[5:]))
                if not all(math.isfinite(value) for value in numbers):
                    raise ValueError('Nonfinite cell value')
                if numbers[0] < 0 or any(value < 0 for value in numbers[2::3]):
                    raise ValueError('Negative cell power/frequency')
                available = row[4] == '1'
                if available:
                    if numbers[0] != power or not 0 < numbers[1] < 1:
                        raise ValueError('Cell power/decay mismatch')
                elif any(numbers):
                    raise ValueError('Unavailable cell carries measurements')
                total += 1
                counts[quiet]['rows'] += 1
                counts[quiet]['available'] += int(available)
                counts[quiet]['nonzero_cells'] += int(any(
                    numbers[i] != 0 for i in range(3, len(numbers)) if (i - 2) % 3))
        if raw.readline():
            raise ValueError('Extra cell rows')
    return dict(frames=frames, rows=total, exact_coverage=True,
                quiet_counts=dict(sorted(counts.items())))


def preflight(corpus, manifest, spec):
    if spec['schema'] != 'm3_quiet_cell_observation_spec_v1' or \
            set(spec['datasets']) != set(DATASETS) or spec['companions'] != list(MODES) or \
            spec['block_samples'] != 512 or spec['flags'] != FLAGS or \
            spec['policy_change'] is not False or spec['installed_output_changed'] is not False or \
            spec['automatic_retry'] is not False:
        raise ValueError('Observation specification mismatch')
    refs = {}
    for dataset in DATASETS:
        path = Path(spec['datasets'][dataset]['reference'])
        ref = json.loads(path.read_text())
        required = {dataset + '.wav', dataset + '.tsv', 'calibration.m3cb', 'templates.tsv'}
        if ref['dataset'] != dataset or set(ref['inputs']) != required:
            raise ValueError('Reference dataset/input set mismatch')
        if ref['settings'] != SETTINGS or ref['block_samples'] != 512 or \
                ref['reference_flags']['current-on'] != FLAGS:
            raise ValueError('Reference settings mismatch')
        verify_inputs(corpus, manifest, dataset)
        for name, identity in ref['inputs'].items():
            if manifest['files'][name] != identity:
                raise ValueError('Input mismatch: ' + name)
        for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
            if manifest['source'][key] != ref['source'][key]:
                raise ValueError('Input provenance mismatch: ' + key)
        refs[dataset] = ref
    return refs


def compress(path, bulk):
    target = path.with_suffix(path.suffix + '.gz')
    item = dict(path=str(target.relative_to(bulk)), raw_bytes=path.stat().st_size,
                raw_sha256=digest(path))
    with path.open('rb') as src, target.open('xb') as dest:
        with gzip.GzipFile(filename='', mode='wb', fileobj=dest, compresslevel=3, mtime=0) as zipped:
            shutil.copyfileobj(src, zipped)
    item.update(bytes=target.stat().st_size, sha256=digest(target))
    path.unlink()
    return item


def run(binary, corpus, manifest, spec, output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    small, bulk = output / 'report', output / 'bulk'
    small.mkdir()
    bulk.mkdir()
    report = dict(schema='m3_quiet_cell_observation_v1', final=False, state='running',
                  stage='input verification', policy_change=False,
                  installed_output_changed=False, promotion_accepted=False, datasets={})

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (small / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    try:
        inputs = json.loads(manifest.read_text())
        frozen = json.loads(spec.read_text())
        refs = preflight(corpus, inputs, frozen)
        report.update(source=inputs['source'], binary_sha256=digest(binary),
                      manifest_sha256=digest(manifest), spec_sha256=digest(spec))
        for dataset in DATASETS:
            ref = refs[dataset]
            entry = report['datasets'][dataset] = dict(
                reference_sha256=digest(Path(frozen['datasets'][dataset]['reference'])),
                historical_v5_sha256=frozen['datasets'][dataset]['v5_sha256'], runs={})
            base = command_for(binary.resolve(), corpus.resolve(), dataset, 'on', 512, None,
                               spectral_lane_collision=True)
            for mode in MODES:
                stem = f'{dataset}-current-on-512-{mode}'
                snapshot, midi, trace, cells = [bulk / (stem + suffix) for suffix in
                    ('.tsv', '-midi.tsv', '-outcome-v5.tsv', '-raw-cells.tsv')]
                command = base + ['--midi-event-trace', str(midi)]
                if mode != 'untraced':
                    command += ['--outcome-trace', str(trace), '--outcome-trace-annotations']
                if mode == 'cells':
                    command += ['--outcome-cell-trace', str(cells)]
                item = entry['runs'][mode] = dict(command=command, state='running')
                report['stage'] = dataset + '/' + mode
                save()
                with snapshot.open('x') as out, (small / (stem + '.stderr')).open('x') as err:
                    subprocess.run(command, stdout=out, stderr=err, check=True, timeout=1200)
                check_identity(snapshot, midi, ref['runs']['current-on'])
                item.update(snapshot_sha256=digest(snapshot), midi_sha256=digest(midi),
                            saved_identity=True)
                paths = [snapshot, midi]
                if mode != 'untraced':
                    item['v5_sha256'] = digest(trace)
                    if item['v5_sha256'] != entry['historical_v5_sha256']:
                        raise ValueError(dataset + '/' + mode + ': historical v5 identity failed')
                    paths.append(trace)
                if mode == 'cells':
                    item['coverage'] = validate_sidecar(trace, cells)
                    paths.append(cells)
                item['evidence'] = [compress(path, bulk) for path in paths]
                item['state'] = 'passed'
                save()
        report.update(state='completed', final=True,
                      stage='snapshot/MIDI/v5 identity and cell coverage passed; analysis pending')
    except Exception as error:
        report.update(state='failed', final=True, error=str(error))
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'spec', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    run(**vars(parser.parse_args()))


if __name__ == '__main__':
    main()
