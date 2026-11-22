"""Level curves around label ends and starts from the two corpus recordings; GitHub Actions CPU only, no model, no weights.

Plan and predictions: docs/recovery/CLAUDE-M3-AUDIO-RELEASE-PROPOSAL-20261122.md.  The worker only measures: nothing is scored here.  The local
analysis (docs/recovery/CLAUDE-M3-AUDIO-RELEASE-20261122.py analyse) joins the saved curves to the pinned ends and evaluates the registered checks.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np

from tools import audio_release_levels as lv


def remote_only():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Recording access requires GitHub Actions')


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def check_hash(path, expected):
    actual = digest(path)
    if actual != expected:
        raise ValueError('Hash mismatch for %s' % Path(path).name)
    return actual


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=1, allow_nan=False) + '\n')
    temporary.replace(path)


def measurement():
    return dict(sample_rate=lv.SOURCE_RATE, window_ms=lv.WINDOW_MS, hop_ms=lv.HOP_MS, harmonics=lv.HARMONICS,
                max_harmonic_hz=lv.MAX_HARMONIC_HZ, end_grid=list(lv.END_GRID), start_grid=list(lv.START_GRID))


def clean(curve):
    return [round(float(v), 2) if np.isfinite(v) else None for v in curve]


def curves_for(x, ends):
    """One entry per end, in the order of the ends file: the end curve and the start curve of its pitch."""
    rows = []
    for e in ends:
        if not (0 <= e['start'] <= e['end'] < len(x)):
            raise ValueError('End %d lies outside the recording' % e['idx'])
        rows.append(dict(idx=e['idx'], midi_note=e['midi_note'],
                         end_levels=clean(lv.end_curve(x, e['midi_note'], e['end'])),
                         start_levels=clean(lv.start_curve(x, e['midi_note'], e['start']))))
    return rows


def captured(command):
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


def run(spec_path, inputs, output):
    remote_only()
    import soundfile as sf
    started = time.time()
    output.mkdir(parents=True)
    report_dir = output / 'report'
    report_dir.mkdir()
    report = dict(schema='m3_audio_release_levels_v1', state='running', final=False, started_at=datetime.now(timezone.utc).isoformat(),
                  corpora={}, model_run=False, installed_output_changed=False, promotion_accepted=False)
    try:
        spec = json.loads(Path(spec_path).read_text())
        if spec['measurement'] != measurement():
            raise ValueError('Implementation settings differ from frozen specification')
        root = Path(__file__).resolve().parents[1]
        source = captured(['git', '-C', str(root), 'rev-parse', 'HEAD'])
        if source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
            raise ValueError('Source or worker dispatch pin mismatch')
        if os.environ.get('INPUT_SHA256') != spec['input_release']['sha256']:
            raise ValueError('Input bundle pin mismatch')
        check_hash(inputs / 'recovery-inputs.json', spec['input_manifest_sha256'])
        ends_path = root / spec['ends']['path']
        check_hash(ends_path, spec['ends']['sha256'])
        ends_file = json.loads(ends_path.read_text())
        if ends_file['sample_rate'] != lv.SOURCE_RATE or set(ends_file['corpora']) != set(spec['datasets']):
            raise ValueError('Ends file differs from the specification')
        report['provenance'] = dict(source_commit=source, worker_repository=os.environ['GITHUB_REPOSITORY'], run_id=os.environ['GITHUB_RUN_ID'],
                                    run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], specification_sha256=digest(spec_path),
                                    ends_sha256=spec['ends']['sha256'], python=sys.version, platform=platform.platform(),
                                    numpy=np.__version__, soundfile=sf.__version__, libsndfile=sf.__libsndfile_version__)
        curves = dict(schema='m3_audio_release_curves_v1', sample_rate=lv.SOURCE_RATE, measurement=measurement(), corpora={})
        for name, config in spec['datasets'].items():
            wav = inputs / 'corpus' / (name + '.wav')
            check_hash(wav, config['wav_sha256'])
            info = sf.info(str(wav))
            if info.samplerate != config['sample_rate'] or info.frames != config['sample_count']:
                raise ValueError('Audio clock differs from specification')
            audio, rate = sf.read(str(wav), dtype='float32', always_2d=True)
            x = audio.mean(axis=1, dtype=np.float32) if audio.shape[1] > 1 else audio[:, 0]     # the streaming path's mono mix
            if rate != lv.SOURCE_RATE or len(x) != config['sample_count']:
                raise ValueError('Decoded audio differs from specification')
            ends = ends_file['corpora'][name]['ends']
            rows = curves_for(x, ends)
            curves['corpora'][name] = dict(ends=rows)
            nan_end = sum(v is None for r in rows for v in r['end_levels'])
            nan_start = sum(v is None for r in rows for v in r['start_levels'])
            finite = [v for r in rows for v in r['end_levels'] if v is not None]
            report['corpora'][name] = dict(ends=len(rows), channels=info.channels, subtype=info.subtype, frames=info.frames,
                                           wav_sha256=config['wav_sha256'], unavailable_end_levels=nan_end, unavailable_start_levels=nan_start,
                                           end_level_min_db=min(finite), end_level_max_db=max(finite))
            print('%s: %d ends measured (%d end and %d start levels unavailable)' % (name, len(rows), nan_end, nan_start), flush=True)
        save_json(report_dir / 'curves.json', curves)
        report['curves_sha256'] = digest(report_dir / 'curves.json')
        report.update(state='completed', final=True, seconds=round(time.time() - started, 1))
    except Exception as error:
        report.update(state='failed', final=True, error='%s: %s' % (type(error).__name__, error))
        raise
    finally:
        save_json(report_dir / 'report.json', report)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--inputs', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    arguments = parser.parse_args()
    run(arguments.spec, arguments.inputs, arguments.output)


if __name__ == '__main__':
    main()
