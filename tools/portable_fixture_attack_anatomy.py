"""Remote-only descriptive curves for the two copied physical unison excerpts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess

from tools.fixture_attack_anatomy import observation_summary
from tools.portable_complex_attack_baseline import extract, sha, verify


def measure(signal, rate, marker, note, conf):
    import numpy as np
    from scipy.signal import butter, hilbert, sosfiltfilt

    size, hop = conf['fft_samples'], conf['hop_samples']
    window = np.hanning(size)
    frequencies = np.fft.rfftfreq(size, 1 / rate)
    factors = np.full(len(frequencies), 2.0)
    factors[[0, -1]] = 1.0
    scale = factors / (size * np.sum(window ** 2))
    bands = [(f'band_{lo}_{hi}', (frequencies >= lo) & (frequencies < hi))
             for lo, hi in conf['bands_hz']]
    covered = np.logical_or.reduce([mask for _, mask in bands])
    fundamental = 440 * 2 ** ((note - 69) / 12)
    width = conf['nominal_relative_half_width']
    sos = butter(4, [fundamental * (1 - width), fundamental * (1 + width)],
                 btype='bandpass', fs=rate, output='sos')
    envelope_power = np.abs(hilbert(sosfiltfilt(sos, signal))) ** 2 / 2
    smooth = round(rate * conf['nominal_smoothing_ms'] / 1000)
    envelope_power = np.convolve(envelope_power, np.ones(smooth) / smooth, mode='same')
    half = round(rate * conf['broad_window_ms'] / 2000)
    start = marker + round(rate * conf['range_ms'][0] / 1000)
    end = marker + round(rate * conf['range_ms'][1] / 1000)
    if start < max(half, size // 2) or end + max(half, size // 2) >= len(signal):
        raise ValueError('Insufficient centered-window context')
    rows, spectrogram, accounting_error = [], [], 0.0
    for center in range(start, end + 1, hop):
        frame = signal[center - size // 2:center + size // 2]
        broad = signal[center - half:center + half]
        power = np.abs(np.fft.rfft(frame * window)) ** 2 * scale
        weighted_power = float(np.sum((frame * window) ** 2) / np.sum(window ** 2))
        band_powers = {name: float(np.sum(power[mask])) for name, mask in bands}
        remainder = float(np.sum(power[~covered]))
        accounting_error = max(accounting_error,
                               abs(sum(band_powers.values()) + remainder - weighted_power))
        row = {'sample': center, 'relative_ms': (center - marker) * 1000 / rate,
               'peak_magnitude': float(np.max(np.abs(broad))),
               'powers': {'broad_rms': float(np.mean(broad ** 2)),
                          'nominal_envelope': float(envelope_power[center]), **band_powers},
               'unreported_band_power': remainder, 'weighted_stft_power': weighted_power}
        rows.append(row)
        spectrogram.append(power)
    if accounting_error > 1e-12:
        raise ValueError('Disjoint STFT bands do not account for weighted power')
    return rows, np.asarray(spectrogram), frequencies, accounting_error


def figure(path, rows, spectrum, frequencies, cues, title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    times = [r['relative_ms'] for r in rows]
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True, constrained_layout=True)
    for name in ('broad_rms', 'nominal_envelope'):
        axes[0].plot(times, [10 * np.log10(r['powers'][name] + 1e-24) for r in rows], label=name)
    axes[0].plot(times, [20 * np.log10(r['peak_magnitude'] + 1e-12) for r in rows],
                 label='10 ms peak', linewidth=0.8, alpha=0.6)
    axes[0].set(title=title, ylabel='Level (dBFS)')
    axes[0].legend(fontsize=8)
    for name in rows[0]['powers']:
        if name.startswith('band_'):
            axes[1].plot(times, [10 * np.log10(r['powers'][name] + 1e-24) for r in rows], label=name)
    axes[1].set_ylabel('Band power (dBFS)')
    axes[1].legend(fontsize=8, ncol=2)
    shown = (frequencies > 0) & (frequencies <= 20000)
    plot = axes[2].pcolormesh(times, frequencies[shown],
                              10 * np.log10(spectrum[:, shown].T + 1e-24),
                              shading='auto', vmin=-100, vmax=-20, cmap='magma')
    axes[2].set(yscale='log', ylim=(60, 20000), ylabel='Frequency (Hz)',
                xlabel='ms relative to approximate first-rise marker')
    fig.colorbar(plot, ax=axes[2], label='Bin power (dBFS)')
    for ax in axes:
        ax.axvline(0, color='grey', linestyle=':', linewidth=1)
        for label, cue in cues.items():
            ax.axvline(cue, color='black', linestyle='--', linewidth=0.8)
        ax.set_xlim(times[0], times[-1])
        ax.grid(alpha=0.15)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source-sha', required=True)
    ap.add_argument('--spec', type=Path, required=True)
    ap.add_argument('--report-archive', type=Path, required=True)
    ap.add_argument('--evidence-archive', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != 'Ajuntanaga/m3-offload':
        raise SystemExit('Audio observation is allowed only on the recorded GitHub worker')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if head != args.source_sha:
        raise SystemExit('Source revision differs')
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'm3_fixture_attack_anatomy_v1', 'source_sha': head,
              'state': 'running', 'final': False, 'started_at': datetime.now(timezone.utc).isoformat(),
              'installed_output_changed': False, 'promotion_accepted': False,
              'acoustic_repluck_preservation': 'not measured', 'observation_only': True,
              'causal_measurement': False, 'integrity': {}, 'datasets': {}}
    try:
        import numpy as np
        import soundfile as sf
        spec = json.loads(args.spec.read_text())
        report['spec'], report['spec_sha256'] = spec, sha(args.spec)
        report['runtime'] = {name: importlib.metadata.version(name)
                             for name in ('numpy', 'scipy', 'soundfile', 'matplotlib')}
        report['stage'] = 'verify archive and source pins'
        verify(args.report_archive, spec['reference_report']['archive_sha256'])
        verify(args.evidence_archive, spec['reference_evidence']['archive_sha256'])
        refpath = args.output / 'reference-report.json'
        extract(args.report_archive, 'controlled-repluck/report.json', refpath,
                spec['reference_report']['report_sha256'])
        reference = json.loads(refpath.read_text())
        if not reference['final'] or not reference['integrity_pass']:
            raise ValueError('Copied-fixture reference is not final with passing integrity')
        report['integrity']['archives_reference'] = True
        for dataset, selected in spec['datasets'].items():
            report['stage'] = 'observe / ' + dataset
            saved = reference['fixtures'][dataset]['fixtures']['single']
            source = reference['fixtures'][dataset]['source']
            if (saved['sha256'] != selected['wave_sha256'] or saved['markers'] != [selected['marker']]
                    or source['sha256'] != selected['source_sha256']
                    or source['marker'] != selected['source_marker']
                    or source['note'] != selected['note']):
                raise ValueError('Fixture source, waveform or marker differs')
            path = args.output / 'fixtures' / dataset / 'single.wav'
            extract(args.evidence_archive, f'fixtures/{dataset}/single.wav', path, selected['wave_sha256'])
            signal, rate = sf.read(path, dtype='float64', always_2d=True)
            if rate != spec['sample_rate'] or signal.shape != (spec['samples'], 1) or not np.isfinite(signal).all():
                raise ValueError('Pinned finite waveform geometry differs')
            rows, spectrum, frequencies, error = measure(signal[:, 0], rate, selected['marker'],
                                                         selected['note'], spec['measurement'])
            curve = args.output / (dataset + '-curves.json.gz')
            with gzip.open(curve, 'wt', encoding='utf-8') as stream:
                json.dump({'rows': rows, 'clock': 'centered noncausal; relative to approximate marker'},
                          stream, allow_nan=False)
            picture = args.output / (dataset + '.png')
            figure(picture, rows, spectrum, frequencies, selected['cues_ms'], dataset)
            report['datasets'][dataset] = {
                'wave_sha256': selected['wave_sha256'], 'source_sha256': selected['source_sha256'],
                'samples': len(signal), 'sample_rate': rate, 'curve_rows': len(rows),
                'curves_file': curve.name, 'curves_sha256': sha(curve),
                'figure_file': picture.name, 'figure_sha256': sha(picture),
                'band_accounting_max_absolute_error': error,
                'cue_neighborhoods': observation_summary(rows, selected['cues_ms'])}
            report['integrity'][dataset + '/pins_geometry_finite'] = True
            report['integrity'][dataset + '/band_accounting'] = error <= 1e-12
        report['integrity_pass'] = all(report['integrity'].values())
        report['state'], report['stage'], report['final'] = 'completed', 'descriptive curves complete', True
        report['decision'] = 'Observation only; acoustic attack count requires interpretation, no detector acceptance'
    except Exception as exc:
        report['state'], report['final'], report['error'] = 'failed', True, repr(exc)
        raise
    finally:
        report['completed_at'] = datetime.now(timezone.utc).isoformat()
        (args.output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: report[key] for key in ('state', 'decision', 'integrity_pass')}))


if __name__ == '__main__':
    main()
