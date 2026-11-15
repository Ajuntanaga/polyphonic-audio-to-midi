"""Capture paired assignment histories for three losses in the forced preview trial.

Native replays run on GitHub. A second of preceding decisions distinguishes
earlier owner changes from the measured label; saved full outputs must match.
"""
import argparse
from pathlib import Path

from tools.portable_forced_pending_string_trial import CONDITIONS
from tools.portable_pending_string_trace import run as capture


CASES = (
    dict(label_index=304, midi_note=46, string_mask=4, start_sample=5630617, end_sample=5702400),
    dict(label_index=332, midi_note=36, string_mask=1, start_sample=6201839, end_sample=6273600),
    dict(label_index=389, midi_note=33, string_mask=1, start_sample=7670639, end_sample=7719715))


def window_for(label):
    return max(0, label['start_sample'] // 64 * 64 - 96000), (label['end_sample'] // 64 + 10) * 64


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    return capture(binary, corpus, manifest_path, reference_path, output,
        timeout=timeout, cases=CASES, conditions=CONDITIONS[1:], window=window_for,
        schema='m3_forced_pending_string_reservation_trace_v1')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference-report', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--replay-timeout-seconds', type=int, default=900)
    args = parser.parse_args()
    if args.replay_timeout_seconds <= 0:
        parser.error('--replay-timeout-seconds must be positive')
    run(args.binary, args.corpus, args.manifest, args.reference_report, args.output,
        timeout=args.replay_timeout_seconds)


if __name__ == '__main__':
    main()
