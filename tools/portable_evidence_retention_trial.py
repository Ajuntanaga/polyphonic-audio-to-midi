"""Cloud-only OFF/ON screen of direct evidence retention through energy dips.

Both replays cover the full ordinary recording. Labels select retained diagnosis
windows only; they never change audio, detector settings or the runtime rule.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from tools.frozen_cue_corpus_gate import compare_replays, read_replay
from tools.portable_assignment_trace import (compress_trace_window, digest, read_rows,
                                             select_labels, trace_sample_bounds, verify_inputs)
from tools.portable_corpus_replay import SETTINGS, command_for


def summarize_target(rows, events, label):
    """Post-lifecycle state and actual MIDI events, distinct from tuner previews."""
    start, end, note = (label[key] for key in ('start_sample', 'end_sample', 'midi_note'))
    expected = set(range(((start + 1 + 63) // 64) * 64 - 1, end, 64))
    seen = set()
    counts = dict(present=0, selected=0, active=0, direct=0,
                  selected_direct_inactive_zero_evidence=0)
    maxima = dict(evidence_ticks=0, attack_ticks=0)
    for row in rows:
        sample = int(row['sample'])
        if not start <= sample < end:
            continue
        if sample not in expected or sample in seen or int(row['tick']) * 64 - 1 != sample:
            raise ValueError('Outcome trace clock or duplicate mismatch')
        seen.add(sample)
        entries = {}
        for item in filter(None, row['candidates'].split(',')):
            fields = item.split(':')
            if len(fields) != 42 or int(fields[0]) in entries:
                raise ValueError('Incompatible outcome candidate schema')
            entries[int(fields[0])] = fields
        fields = entries.get(note)
        if fields is None:
            continue
        selected, active, direct = int(fields[1]) == 4, bool(int(fields[2])), bool(int(fields[10]))
        evidence, attack = int(fields[26]), int(fields[24])
        counts['present'] += 1
        counts['selected'] += selected
        counts['active'] += active
        counts['direct'] += direct
        counts['selected_direct_inactive_zero_evidence'] += selected and direct and not active and not evidence
        maxima['evidence_ticks'] = max(maxima['evidence_ticks'], evidence)
        maxima['attack_ticks'] = max(maxima['attack_ticks'], attack)
    if seen != expected:
        raise ValueError('Incomplete outcome trace for target label')
    transitions = []
    for row in events:
        if row['kind'] not in ('on', 'off'):
            raise ValueError('Unknown MIDI event kind')
        if int(row['note']) == note and start <= int(row['sample']) < end:
            transitions.append(dict(sample=int(row['sample']), kind=row['kind'],
                                    voice_id=int(row['voice_id'])))
    return dict(label=label, frames=len(seen), counts=counts, maxima=maxima,
                midi_events_during_label=transitions,
                interpretation='Candidate state is after lifecycle processing. MIDI events are '
                               'actual transitions; neither proves the correct physical string '
                               'or freedom from stuck notes. Labeled matches are scored separately.')


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    report = dict(schema='m3_direct_evidence_retention_trial_v1', state='running', final=False,
                  stage='verify inputs', dataset='ordinary', settings=SETTINGS,
                  installed_output_changed=False, promotion_accepted=False,
                  native_timing='not measured', live_readiness='not measured')

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    def replay(command, stem):
        report.update(stage=stem, command=command)
        save()
        path = output / (stem + '.tsv')
        started = time.monotonic()
        with path.open('x') as stdout, (output / (stem + '.stderr')).open('x') as stderr:
            subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=timeout)
        parsed = read_replay(path)
        report.setdefault('runs', {})[stem] = dict(elapsed_seconds=time.monotonic() - started,
            tsv_sha256=digest(path), output=parsed['output'],
            exact_matches_by_string_count=parsed['exact_matches_by_string_count'])
        return path, parsed

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        verify_inputs(corpus, manifest, 'ordinary')
        report.update(source=manifest.get('source', {}), binary_sha256=digest(binary),
                      input_manifest_sha256=digest(manifest_path),
                      reference_report_sha256=digest(reference_path))
        command = command_for(binary, corpus, 'ordinary', 'off', 512, None)
        reference_file, before = replay(command, 'reference-off')
        reference = json.loads(reference_path.read_text())['runs']['reference-off']
        identity = (digest(reference_file) == reference['tsv_sha256']
                    and before['output'] == reference['output'])
        report['off_reference_bit_identical'] = identity
        if not identity:
            raise ValueError('OFF reference differs from the retained ordinary baseline')
        label = select_labels(before['labels'], note=42, label_index=55)[0]
        with reference_file.open() as stream:
            aggregate = next(csv.DictReader(stream, delimiter='\t'))
        samples, rate = int(aggregate['samples']), int(aggregate['sample_rate'])
        start, end = trace_sample_bounds([label], samples)
        traces = {kind: output / (kind + '.tsv') for kind in ('candidate', 'outcome', 'midi-event')}
        command.append('--diagnostic-direct-evidence-retention')
        for kind, path in traces.items():
            command.extend(('--' + kind + '-trace', str(path)))
        command.extend(('--candidate-trace-note', '42', '--candidate-trace-start', str(start / rate),
                        '--candidate-trace-end', str(end / rate)))
        _, after = replay(command, 'trial-on')
        comparison = compare_replays(before, after)
        report.update(comparison=comparison, sample_rate=rate, sample_count=samples,
                      target_before=label, target_after=after['labels'][55],
                      full_recording_screen_pass=comparison['gate_pass'],
                      labeled_match_gain=comparison['delta']['matched'] > 0)
        # Stream the full capture once; retain the small target window in memory.
        window = []
        with traces['outcome'].open(newline='') as stream:
            rows = csv.DictReader((line for line in stream if not line.startswith('#')), delimiter='\t')
            expected_sample = 63
            for row in rows:
                sample = int(row['sample'])
                if sample != expected_sample or int(row['tick']) * 64 - 1 != sample:
                    raise ValueError('Incomplete or reordered full outcome capture')
                expected_sample += 64
                if start <= sample < end:
                    window.append(row)
            if expected_sample != 63 + (samples // 64) * 64:
                raise ValueError('Incomplete full outcome capture')
        report['target_lifecycle'] = summarize_target(window, read_rows(traces['midi-event']), after['labels'][55])
        report['traces'] = {}
        for kind, path in traces.items():
            report['traces'][kind] = compress_trace_window(path, start=start, end=end)
            path.unlink()
        report.update(state='completed', final=True, stage='offline screen collected',
                      decision='eligible for wider validation' if comparison['gate_pass'] and
                               comparison['delta']['matched'] > 0 else 'rejected')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()


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
