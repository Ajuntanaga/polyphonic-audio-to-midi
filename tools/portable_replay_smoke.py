"""Generated-audio CI transport/parity check, not a physical-corpus acceptance gate."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import wave

from tools.frozen_cue_corpus_gate import read_replay, compare_replays


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rate, count = 96000, 192000
    wav = args.output / 'generated-smoke.wav'
    with wave.open(str(wav), 'wb') as stream:
        stream.setparams((1, 2, rate, count, 'NONE', 'not compressed'))
        stream.writeframes(b''.join(struct.pack('<h', round(6000 * math.sin(
            2 * math.pi * 65.40639132514966 * i / rate))) if 24000 <= i < 144000
            else b'\0\0' for i in range(count)))
    labels = args.output / 'generated-smoke.tsv'
    labels.write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n24000\t144000\t36\t1\n')
    report = dict(kind='generated-smoke-only', physical_corpus_accepted=False,
                  binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(), runs={})
    passed = True
    for mode in ('off', 'on'):
        reference = None
        for block in (32, 512, 1024):
            output = args.output / f'{mode}-{block}.tsv'
            command = [str(args.binary.resolve()), '--wav', str(wav), '--labels', str(labels),
                       '--block', str(block), '--label-details']
            if mode == 'on':
                command.append('--diagnostic-native-partial-cues')
            with output.open('w') as stream:
                subprocess.run(command, stdout=stream, check=True, timeout=120)
            result = read_replay(output)
            reference = result if reference is None else reference
            parity = compare_replays(reference, result)
            exact = parity['output_bit_identical'] and not parity['changed_labels']
            passed &= exact
            report['runs'][f'{mode}-{block}'] = dict(output=result['output'], exact_buffer_parity=exact)
    report['passed'] = passed
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not passed:
        raise SystemExit('Generated replay changed across buffer sizes')


if __name__ == '__main__':
    main()
