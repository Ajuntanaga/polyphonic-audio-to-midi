"""Bounded oracle component measurement; run recorded inputs on GHA only.

Reconstructs a saved PCM16 mixture before reporting component levels. Labels
select source excerpts for diagnosis only; none of these values enter the DSP.
"""
import argparse
import csv
import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from tools.generate_note_combination_corpus import (
    available_sample_count, materialize_assignment, mix_real_excerpts,
    read_note_catalog, synchronized_label_rows,
)


def check_saved_labels(path, labels, case_start, hold_samples):
    """Require the complete saved passage, including detuning, to agree."""
    def key(row):
        return (int(row['start_sample']), int(row['end_sample']),
                int(row['midi_note']), int(row['string_mask']),
                int(row['calibration_pass']), float(row['expected_cents']))
    with path.open(newline='') as stream:
        actual = [key(row) for row in csv.DictReader(stream, delimiter='\t')
                  if int(row['start_sample']) < case_start + hold_samples
                  and int(row['end_sample']) > case_start]
    expected = [(a, b, n.midi_note, n.string_mask, n.calibration_pass,
                 n.expected_cents) for a, b, n in labels]
    if sorted(actual) != sorted(expected):
        raise ValueError('saved passage labels do not match source mapping')


def measure(sources, notes, saved_pcm, sample_rate, interval):
    count = len(saved_pcm)
    rendered = mix_real_excerpts(sources, notes, count)
    pcm = np.rint(rendered * 32767.0).astype('<i2')
    if saved_pcm.dtype != np.int16 or not np.array_equal(pcm, saved_pcm):
        raise ValueError('saved mixture reconstruction is not bit-identical')
    begin, end = interval
    if not 0 <= begin < end <= count:
        raise ValueError('invalid measurement interval')
    components = []
    for item in notes:
        component = np.zeros(count, dtype=np.float64)
        n = available_sample_count(sources[item.physical_string], item, count)
        component[item.offset_samples:item.offset_samples+n] = sources[item.physical_string][item.start_sample:item.start_sample+n]
        components.append(component)
    summed = np.sum(components, axis=0) / np.sqrt(len(notes))
    peak = float(np.max(np.abs(summed)))
    gain = (0.999 / peak if peak > 1 else 1.0) / np.sqrt(len(notes))
    rows = []
    for item, component in zip(notes, components):
        x = component[begin:end] * gain
        frequency = 440 * 2 ** ((item.midi_note - 69 + (item.expected_cents or 0)/100) / 12)
        t = np.arange(len(x)) / sample_rate
        window = np.hanning(len(x))
        amplitudes = [float(2 * abs(np.dot(x * window, np.exp(-2j*np.pi*frequency*h*t))) / window.sum()) for h in range(1, 7)]
        rows.append(dict(source=dataclasses.asdict(item), rms=float(np.sqrt(np.mean(x*x))), peak=float(np.max(np.abs(x))), harmonic_projection_amplitudes=amplitudes))
    return dict(reconstruction_identical=True, pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest(), interval=list(interval), common_gain=gain, components=rows, limits='Oracle source levels and fixed-frequency Hann projections, not runtime resonator energies, source separation, MIDI gain or real-time acceptance. Component powers omit cross terms.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--labels', type=Path, required=True)
    p.add_argument('--audio', type=Path, required=True)
    p.add_argument('--mixture', type=Path, required=True)
    p.add_argument('--mixture-labels', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--case-start', type=int, required=True)
    p.add_argument('--hold-samples', type=int, required=True)
    p.add_argument('--case-index', type=int, required=True)
    p.add_argument('--frets', type=int, nargs=8, required=True)
    args = p.parse_args()
    notes = materialize_assignment(read_note_catalog(args.labels), args.frets, args.case_index % 3)
    rate, saved = wavfile.read(args.mixture, mmap=True)
    sources = {}
    for item in notes:
        r, x = wavfile.read(args.audio / f'string-{item.physical_string:02d}-raw.wav', mmap=True)
        if r != rate or x.ndim != 1:
            raise ValueError('source sample clock or channel mismatch')
        if np.issubdtype(x.dtype, np.integer):
            x = x.astype(np.float32) / float(max(abs(np.iinfo(x.dtype).min), np.iinfo(x.dtype).max))
        sources[item.physical_string] = x
    labels = synchronized_label_rows(sources, notes, args.hold_samples, args.case_start)
    check_saved_labels(args.mixture_labels, labels, args.case_start, args.hold_samples)
    interval = (labels[0][0]-args.case_start, labels[0][1]-args.case_start)
    report = measure(sources, notes, saved[args.case_start:args.case_start+args.hold_samples], rate, interval)
    report['case_start'] = args.case_start
    report['saved_labels_identical'] = True
    report['expected_labels'] = [dict(start=a, end=b, note=n.midi_note, mask=n.string_mask, calibration_pass=n.calibration_pass) for a,b,n in labels]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
