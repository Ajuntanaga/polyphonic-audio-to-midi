"""GHA-only isolated parent repeatability, with unchanged production settings."""
import argparse
import csv
import json
import os
from collections import Counter
from pathlib import Path
import subprocess
import numpy as np
from tools.controlled_descriptor_overlap import read_float_wave, write_float_wave
from tools.portable_runtime_harmonic_identity import digest, summarize_trace
from tools.portable_runtime_profile_generalization import measurement_bounds
from tools.portable_corpus_replay import SETTINGS
from tools.frozen_cue_corpus_gate import read_replay, compare_replays
from tools.octave_parent_measurement import production_harmonics, six_frequency_energy, held_pass_errors


def validate_inventory(data):
    takes = data['takes']
    if Counter(t['note'] for t in takes) != {44:19, 48:24, 60:33, 62:12, 69:8}:
        raise ValueError('Expected all 96 frozen takes')
    identities = {(t['label_file'], t['label_index']) for t in takes}
    if len(identities) != len(takes):
        raise ValueError('Duplicate take')
    for t in takes:
        if (t['lane'] not in range(8) or t['held_pass'] not in (1,2,3) or
            not 0 <= t['start_sample'] < t['end_sample'] or
            t['production_harmonics'] != production_harmonics(t['note'])):
            raise ValueError('Invalid take contract')
    return takes


def take_measurement_bounds(start, end, rate):
    prefix = round(.250 * rate)
    if not prefix <= start < end:
        raise ValueError('Invalid source bounds')
    try:
        return measurement_bounds(prefix, prefix + end - start, rate)
    except ValueError:
        return None  # Keep this take unavailable; do not move the frozen window.


def run(binary, inputs, inventory, sources, output):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Recorded processing must run on GitHub Actions')
    data = json.loads(inventory.read_text())
    takes = validate_inventory(data)
    # Sources maps raw basenames to pinned sha256 and sample_rate_hz.
    pins = json.loads(sources.read_text())
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, state='running', final=False, measurements=[],
        inventory_sha256=digest(inventory), sources_sha256=digest(sources),
        binary_sha256=digest(binary), source_revision=os.environ.get('M3_SOURCE_SHA'),
        settings=SETTINGS, installed_output_changed=False, promotion_accepted=False,
        limitations=['Known-pitch fixed-frequency projections are not runtime cells or source separation.',
                    '320-480ms after label start, not verified onset; clip-local state.',
                    'Same-session whole-pass holdout with correct lane supplied.',
                    'No chord discrimination, allocation, timing or live-host acceptance.'])
    def save():
        (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    save()
    try:
        for label_file in sorted({t['label_file'] for t in takes}):
            name = Path(label_file).name
            label_path = inputs/'labels'/name
            if digest(label_path) != data['label_sha256'][label_file]:
                raise ValueError('Label hash mismatch: '+name)
            with label_path.open() as stream:
                labels = list(csv.DictReader(stream, delimiter='\t'))
            raw_name = Path(name).stem+'-raw.wav'
            raw = inputs/'raw'/raw_name
            raw_hash = digest(raw)
            if raw_hash != pins[raw_name]['sha256']:
                raise ValueError('Raw input hash mismatch: '+raw_name)
            rate, audio = read_float_wave(raw)
            if rate != pins[raw_name]['sample_rate_hz']:
                raise ValueError('Sample rate mismatch')
            for take in (t for t in takes if t['label_file'] == label_file):
                label = labels[take['label_index']]
                expected = dict(start_sample=take['start_sample'], end_sample=take['end_sample'],
                                midi_note=take['note'], string_mask=1 << take['lane'], calibration_pass=take['held_pass'])
                if any(int(label[k]) != v for k,v in expected.items()) or float(label['expected_cents']) != take['expected_cents']:
                    raise ValueError('Inventory differs from pinned label')
                prefix = round(.250*rate)
                start,end = take['start_sample'],take['end_sample']
                if not prefix <= start < end <= len(audio):
                    raise ValueError('Invalid source bounds')
                bounds = take_measurement_bounds(start, end, rate)
                take_id = f'{Path(name).stem}-label{take["label_index"]}'
                if bounds is None:
                    report['measurements'].append(dict(**take, take_id=take_id,
                        raw_sha256=raw_hash, available=False,
                        unavailable_reason='incomplete_fixed_measurement_window',
                        runtime_energy=None, projection_energy=None,
                        comparison=None, midi_bit_identical=None))
                    save()
                    continue
                begin,stop = bounds
                folder = output/take_id
                folder.mkdir()
                # Retain only through the fixed measurement endpoint.
                samples = audio[start-prefix:start-prefix+stop]
                wave = folder/'clip.wav'
                write_float_wave(wave, rate, samples)
                target = folder/'labels.tsv'
                target.write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n'+f'{prefix}\t{stop}\t{take["note"]}\t{1 << take["lane"]}\n')
                command = [str(binary.resolve()), '--wav',str(wave.resolve()), '--labels',str(target.resolve()), '--block','512','--label-details']
                for k,v in SETTINGS.items():
                    command += ['--'+k,str(v)]
                for mode in ('reference','traced'):
                    args = command + ['--midi-event-trace',str((folder/(mode+'-midi.tsv')).resolve())]
                    if mode == 'traced':
                        args += ['--candidate-trace',str((folder/'candidate.tsv').resolve()), '--candidate-trace-note',str(take['note']), '--candidate-trace-start','0', '--candidate-trace-end',str(stop/rate)]
                    with (folder/(mode+'.tsv')).open('x') as out, (folder/(mode+'.stderr')).open('x') as err:
                        subprocess.run(args, stdout=out, stderr=err, check=True, timeout=90)
                comparison = compare_replays(read_replay(folder/'reference.tsv'),read_replay(folder/'traced.tsv'))
                midi_same = digest(folder/'reference-midi.tsv') == digest(folder/'traced-midi.tsv')
                if not comparison['output_bit_identical'] or comparison['changed_labels'] or not midi_same:
                    raise ValueError('Tracing changed output')
                with (folder/'candidate.tsv').open() as stream:
                    rows = [r for r in csv.DictReader(stream, delimiter='\t') if begin <= int(r['sample']) < stop]
                runtime = summarize_trace(rows, begin, rate, harmonics=production_harmonics(take['note']))
                half = round(.080*rate)
                projections = [six_frequency_energy(samples[b:b+half],rate,take['note'],take['expected_cents']) for b in (begin,begin+half)]
                report['measurements'].append(dict(**take, take_id=take_id, raw_sha256=raw_hash,
                    clip_sha256=digest(wave), runtime=runtime,
                    runtime_energy=np.mean(runtime['mean_energy_per_half'],axis=0).tolist() if runtime['eligible'] else None,
                    projection_energy=np.mean(projections,axis=0).tolist(), projection_energy_per_half=projections,
                    comparison=comparison, midi_bit_identical=midi_same))
                save()
        report['held_pass'] = {field:held_pass_errors(report['measurements'],field) for field in ('runtime_energy','projection_energy')}
        report.update(state='completed',final=True)
    except Exception as error:
        report.update(state='failed',final=True,error=str(error))
        raise
    finally:
        save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('binary','inputs','inventory','sources','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    run(**vars(parser.parse_args()))
