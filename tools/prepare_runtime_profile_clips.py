"""Extract frozen multi-pitch clips on GitHub Actions, without moving labels."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from tools.controlled_descriptor_overlap import read_float_wave, write_float_wave
from tools.portable_runtime_profile_generalization import validate_manifest


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def extract(plan, inputs, output):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Recorded extraction must run on GitHub Actions')
    entries = plan['clips']
    if len(entries) != 91 or len({c['segment_id'] for c in entries}) != 91:
        raise ValueError('Expected 91 unique frozen segments')
    output.mkdir(parents=True, exist_ok=False)
    clips = []
    # Read one raw excerpt at a time; never normalize or resample its samples.
    for raw_name in sorted({Path(c['raw_wave']).name for c in entries}):
        group = [c for c in entries if Path(c['raw_wave']).name == raw_name]
        wave = inputs / raw_name
        actual_hash = sha256(wave)
        if any(c['recorded_raw_wave_sha256'] != actual_hash for c in group):
            raise ValueError('Raw excerpt hash mismatch: '+raw_name)
        rate, samples = read_float_wave(wave)
        for c in group:
            begin, end = c['start_sample'], c['end_sample']
            prefix = round(rate * .250)
            if rate != c['sample_rate_hz'] or not prefix <= begin < end <= len(samples):
                raise ValueError('Invalid frozen source interval: '+c['segment_id'])
            name = f"s{c['string']}-n{c['midi_note']}-label{c['label_index']}.wav"
            target = output / name
            if target.exists():
                raise ValueError('Duplicate output name')
            write_float_wave(target, rate, samples[begin-prefix:end])
            clips.append(dict(clip=name, string=c['string'], midi_note=c['midi_note'],
                **{'pass':c['calibration_pass']}, labeled_begin=prefix,
                labeled_end=prefix+end-begin, sha256=sha256(target),
                segment_id=c['segment_id'], source_start_sample=begin-prefix,
                source_end_sample=end, source_wave_sha256=actual_hash,
                sample_rate_hz=rate, onset_verified=False))
    result = dict(schema=1, clips=clips, source=plan.get('source', {}),
                  extraction='Unmodified raw samples; 250 ms pre-roll; frozen label bounds')
    validate_manifest(result)
    (output/'manifest.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('plan', 'inputs', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    extract(json.loads(args.plan.read_text()), args.inputs, args.output)
