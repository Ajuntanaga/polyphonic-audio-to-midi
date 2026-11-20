"""GHA-only actual replay-cell probe with known synthetic harmonic powers."""
from __future__ import annotations
import argparse
import csv
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import numpy as np
from tools.portable_runtime_harmonic_identity import digest, summarize_trace
from tools.portable_corpus_replay import SETTINGS
from tools.frozen_cue_corpus_gate import read_replay, compare_replays


def write_float_wave(path, samples, rate):
    data = np.asarray(samples, dtype='<f4').tobytes()
    fmt = struct.pack('<HHIIHH', 3, 1, rate, rate * 4, 4, 32)
    path.write_bytes(b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVEfmt ' +
                     struct.pack('<I', 16) + fmt + b'data' + struct.pack('<I', len(data)) + data)


def run(binary, output):
    output.mkdir(parents=True, exist_ok=False)
    rate, begin = 96000, 24000
    report = dict(schema='m3_harmonic_leakage_probe_v1', state='running', final=False,
                  binary_sha256=digest(binary), settings=SETTINGS, measurements=[],
                  source_commit=os.environ.get('SOURCE_SHA'),
                  worker_commit=os.environ.get('GITHUB_SHA'),
                  run_id=os.environ.get('GITHUB_RUN_ID'),
                  installed_output_changed=False, promotion_accepted=False,
                  limitations=['Synthetic isolated note52 only; no corpus or host acceptance.',
                               'Known input powers are not finite-window cell powers.',
                               'Phase-valid and invalid ticks must be interpreted separately.'])
    def save():
        (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    save()
    try:
        for cents in (0, -20):
            for h2_power in (0, 2e-5, 1e-3):
                for relative_phase in (0, math.pi / 2):
                    directory = output / f'c{cents}_h2{h2_power}_p{relative_phase:.4f}'
                    directory.mkdir()
                    frequency = 440 * 2 ** ((52 - 69) / 12 + cents / 1200)
                    t = np.arange(rate) / rate
                    tone = .2 * (np.sin(2 * np.pi * frequency * t) + math.sqrt(h2_power) *
                                  np.sin(4 * np.pi * frequency * t + relative_phase))
                    samples = np.concatenate((np.zeros(begin), tone, np.zeros(9600)))
                    wav = directory / 'input.wav'
                    write_float_wave(wav, samples, rate)
                    labels = directory / 'labels.tsv'
                    labels.write_text(f'start_sample\tend_sample\tmidi_note\tstring_mask\n{begin}\t{begin+rate}\t52\t1\n')
                    base = [str(binary.resolve()), '--wav', str(wav.resolve()), '--labels', str(labels.resolve()), '--block', '512', '--label-details']
                    for key, value in SETTINGS.items():
                        base += ['--' + key, str(value)]
                    for mode in ('reference', 'traced'):
                        command = base + ['--midi-event-trace', str((directory / (mode + '-midi.tsv')).resolve())]
                        if mode == 'traced':
                            command += ['--candidate-trace', str((directory / 'candidate.tsv').resolve()), '--candidate-trace-note', '52',
                                        '--candidate-trace-start', '.25', '--candidate-trace-end', '1.25']
                        with (directory / (mode + '.tsv')).open('x') as stdout, (directory / (mode + '.stderr')).open('x') as stderr:
                            subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=90)
                    comparison = compare_replays(read_replay(directory / 'reference.tsv'), read_replay(directory / 'traced.tsv'))
                    midi_identity = digest(directory / 'reference-midi.tsv') == digest(directory / 'traced-midi.tsv')
                    if not comparison['output_bit_identical'] or comparison['changed_labels'] or not midi_identity:
                        raise ValueError('Tracing changed output')
                    with (directory / 'candidate.tsv').open() as stream:
                        rows = list(csv.DictReader(stream, delimiter='\t'))
                    windows = []
                    for offset in (0, 38400, 76800):
                        start = begin + offset
                        selected = [r for r in rows if start <= int(r['sample']) < start + 15360]
                        if not selected:
                            raise ValueError('Missing candidate trace window')
                        windows.append(dict(offset_samples=offset, all=summarize_trace(selected, start, rate),
                                            by_phase_valid={str(valid): summarize_trace([r for r in selected if int(r['phase_valid']) == valid], start, rate) for valid in (0, 1)}))
                    report['measurements'].append(dict(cents=cents, h2_input_power_ratio=h2_power,
                                                       h2_phase=relative_phase, windows=windows,
                                                       comparison=comparison, midi_bit_identical=midi_identity,
                                                       input_sha256=digest(wav), trace_sha256=digest(directory / 'candidate.tsv')))
                    save()
        report.update(state='completed', final=True)
    except Exception as error:
        report.update(state='failed', final=True, error=str(error))
        raise
    finally:
        save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.binary, args.output)
