"""One native joint-release screen on GitHub; no model execution or promotion.

The support clock is the measured FIFO completion clock of the pinned model
events. The source of the support is external to the timed native processor.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

from tools.frozen_cue_corpus_gate import read_replay, compare_replays
from tools.midi_lifecycle_analysis import read_events, summarize, raw_conflicts
from tools.pitch_detector_comparison import native_spans, score, compare
from tools.portable_assignment_trace import digest, verify_inputs
from tools.portable_corpus_replay import SETTINGS, command_for, timing_gates
from tools.portable_weak_note_residual_trace import check_identity

RATE = 96000
COUNTERS = ('eligible', 'warmup', 'model_veto', 'released', 'refused', 'reactivated')
FALSE = ('false_wrong_note_voice_samples', 'false_wrong_string_voice_samples',
         'false_gap_voice_samples')


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def check_file(path, pin):
    if path.stat().st_size != pin['bytes'] or digest(path) != pin['sha256']:
        raise ValueError('Pinned file differs: ' + str(path))


def support_table(document, sample_count):
    """Ceiling to samples, original tie order, no EOF-off or future event use."""
    rows, active, previous, omitted = [], set(), -1, 0
    for event in document['events']:
        ns, note, kind = event['emitted_ns'], event['note'], event['kind']
        if (type(ns) is not int or ns < previous or ns < 0
                or type(note) is not int or not 0 <= note <= 127
                or kind not in ('on', 'off')):
            raise ValueError('Invalid or unordered model event')
        previous = ns
        if (kind == 'on') == (note in active):
            raise ValueError('Unpaired model event')
        if kind == 'on':
            active.add(note)
        else:
            active.remove(note)
        sample = (ns * RATE + 999999999) // 1000000000
        if sample < sample_count:
            rows.append(f'{sample}\t{int(kind == "on")}\t{note}\n')
        else:
            omitted += 1
    return ('m3_joint_release_support_v1\t96000\n' + ''.join(rows),
            dict(events=len(document['events']), delivered_events=len(rows),
                 beyond_recording_events=omitted, open_after_event_file=sorted(active),
                 clock='ceil(emitted_ns * 96000 / 1e9), apply before sample',
                 eof_policy='No invented NoteOff; final open support is retained.'))


def label_budget(pairs, rate=RATE):
    """pairs: label index, CURRENT value, candidate value. Both limits apply."""
    failures, new_misses = [], []
    for index, before, after in pairs:
        if any(type(x) is not int or x < 0 for x in (index, before, after)):
            raise ValueError('Invalid label sample count')
        loss = max(0, before - after)
        if before and not after:
            new_misses.append(index)
        if loss * 1000 > 25 * rate or loss * 20 > before:
            failures.append(dict(label_index=index, before=before, after=after,
                                 lost_samples=loss, lost_ms=1000 * loss / rate,
                                 relative_loss=loss / before))
    return dict(passed=not failures and not new_misses, failures=failures,
                newly_completely_missed=new_misses, maximum_loss_ms=25,
                maximum_relative_loss=0.05)


def parse_counters(stderr):
    found = re.findall(r'^m3_replay: joint_rapid_release (.+)$', stderr, re.MULTILINE)
    if len(found) != 1:
        raise ValueError('Missing or repeated joint release counters')
    result = dict((key, int(value)) for key, value in
                  (item.split('=') for item in found[0].split()))
    if set(result) != set(COUNTERS) or any(v < 0 for v in result.values()):
        raise ValueError('Invalid joint release counters')
    if (result['eligible'] != sum(result[k] for k in
            ('warmup', 'model_veto', 'released', 'refused'))
            or result['reactivated'] > result['released']):
        raise ValueError('Joint release counter accounting differs')
    return result


def fetch_support(spec, bulk, logs):
    archive = bulk / 'support-source.zip'
    # Capture first; never parse CLI output as JSON or retry an ambiguous fetch.
    with archive.open('xb') as stdout, (logs / 'support-download.stderr').open('x') as stderr:
        subprocess.run(['gh', 'api', f'repos/{spec["repository"]}/actions/artifacts/'
                        f'{spec["artifact"]["id"]}/zip'], stdout=stdout, stderr=stderr,
                       check=True, timeout=180)
    check_file(archive, spec['artifact'])
    result = {}
    with zipfile.ZipFile(archive) as zipped:
        for name, config in spec['datasets'].items():
            pin = config['support']
            matches = [n for n in zipped.namelist()
                       if n == pin['member'] or n.endswith('/' + pin['member'])]
            if len(matches) != 1 or zipped.getinfo(matches[0]).file_size != pin['bytes']:
                raise ValueError('Support archive member differs: ' + name)
            payload = zipped.read(matches[0])
            if hashlib.sha256(payload).hexdigest() != pin['sha256']:
                raise ValueError('Support event digest differs: ' + name)
            destination = bulk / (name + '-model-events.json')
            destination.write_bytes(payload)
            result[name] = destination
    archive.unlink()  # Our verified temporary copy; event members are retained.
    return result


def evaluate(reference, trial):
    pitch = compare(reference['pitch'], trial['pitch'])
    budgets = {}
    for metric in ('present_samples', 'longest_present_samples'):
        budgets['pitch_' + metric] = label_budget([
            (a['label_index'], a[metric], b[metric])
            for a, b in zip(reference['pitch']['labels'], trial['pitch']['labels'])])
    # Routing holds remain visible and protected, separately from pitch presence.
    for metric in ('exact_held_samples', 'longest_exact_hold_samples'):
        budgets[metric] = label_budget([
            (a['label_index'], a[metric], b[metric])
            for a, b in zip(reference['lifecycle']['labels'], trial['lifecycle']['labels'])])
    before, after = (x['lifecycle']['output_safety']['counts'] for x in (reference, trial))
    deltas = {key: after[key] - before[key] for key in before}
    retriggers = [dict(label_index=a['label_index'],
                  delta=b['retrigger_note_ons_inside_label'] - a['retrigger_note_ons_inside_label'])
                  for a, b in zip(reference['lifecycle']['labels'], trial['lifecycle']['labels'])
                  if b['retrigger_note_ons_inside_label'] > a['retrigger_note_ons_inside_label']]
    snapshot = compare_replays(reference['snapshot'], trial['snapshot'])
    gates = dict(label_budget=all(b['passed'] for b in budgets.values()),
        raw_false_nonincrease=all(deltas[k] <= 0 for k in FALSE),
        snapshot_false_nonincrease=all(trial['snapshot']['output'][k] <= reference['snapshot']['output'][k]
            for k in ('false_wrong_note_voices', 'false_wrong_string_voices', 'false_gap_voices')),
        pitch_set_noninferiority=all(pitch['sample_deltas'][k] >= 0 for k in
            ('exact_pitch_set_samples', 'all_expected_pitches_samples')),
        valid_pairing=all(x['lifecycle']['coverage_valid'] for x in (reference, trial)),
        retriggers_nonincrease=not retriggers,
        raw_conflicts_nonincrease=all(trial['conflicts']['counts'][k] <= v
            for k, v in reference['conflicts']['counts'].items()))
    gap = before['false_gap_voice_samples']
    return dict(pitch=pitch, snapshot=snapshot, label_budgets=budgets,
        raw_output_deltas=deltas, retrigger_increases=retriggers, gates=gates,
        gap_reduction_fraction=(gap-after['false_gap_voice_samples'])/gap if gap else None,
        eof_interpretation='Open owners are reported, not inferred stuck MIDI; external host release unverified.')


def run(args):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Native execution and artifact transfer are GitHub-only')
    args.output.mkdir(parents=True, exist_ok=False)
    bulk, logs = args.output / 'bulk', args.output / 'report'
    bulk.mkdir(); logs.mkdir()
    report_path = logs / 'report.json'
    report = dict(schema='m3_joint_rapid_reset_v1', state='running', final=False,
        installed_output_changed=False, promotion_accepted=False, datasets={},
        settings=SETTINGS, limits='Two design recordings only; fixed external model events. '
        'Model runtime cost, host integration, generalization and live readiness are not established.')

    def checkpoint(stage):
        report.update(stage=stage, updated_at=datetime.now(timezone.utc).isoformat())
        save(report_path, report)

    try:
        spec = json.loads(args.spec.read_text())
        if (spec['budget'] != dict(maximum_loss_ms=25, maximum_relative_loss=0.05)
                or spec['ordinary_gap_reduction_minimum'] != .20
                or list(spec['datasets']) != ['ordinary', 'extended-middle']):
            raise ValueError('Frozen screen changed')
        manifest = json.loads(args.manifest.read_text())
        report.update(source=manifest['source'], binary_sha256=digest(args.binary),
            spec_sha256=digest(args.spec), manifest_sha256=digest(args.manifest),
            support_artifact=spec['artifact'])
        checkpoint('fetch pinned event members')
        supports = fetch_support(spec, bulk, logs)
        for name, config in spec['datasets'].items():
            reference_path = Path(config['reference'])
            saved = json.loads(reference_path.read_text())
            verify_inputs(args.corpus, manifest, name)
            if (saved['dataset'] != name or saved['settings'] != SETTINGS
                    or saved['block_samples'] != 512 or
                    saved['reference_flags']['current-on'] != ['--diagnostic-spectral-lane-collision']):
                raise ValueError('Reference configuration differs')
            for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
                if saved['source'][key] != manifest['source'][key]:
                    raise ValueError('Input provenance differs: ' + key)
            for filename, pin in saved['inputs'].items():
                check_file(args.corpus / filename, pin)
            pin = saved['runs']['current-on']
            count = pin['sample_count']
            if pin['sample_rate'] != RATE:
                raise ValueError('Reference sample rate differs')
            text, support_audit = support_table(json.loads(supports[name].read_text()), count)
            support = bulk / (name + '-support.tsv')
            support.write_text(text)
            dataset = dict(reference_sha256=digest(reference_path), support=support_audit,
                support_sha256=digest(support), runs={}, arms={})
            report['datasets'][name] = dataset
            for arm in ('current', 'trial'):
                base_snapshot = None
                for block, timed in ((512, False), (32, True), (1024, True), (512, True)):
                    stem = f'{name}-{arm}-{block}' + ('-timed' if timed else '')
                    snapshot, midi = bulk / (stem + '.tsv'), bulk / (stem + '-midi.tsv')
                    timing = logs / (stem + '-timing.json')
                    stderr = logs / (stem + '.stderr')
                    command = command_for(args.binary, args.corpus, name, 'on', block,
                        timing, spectral_lane_collision=True, midi_trace=None if timed else midi)
                    if timed and block != 32:
                        command.extend(('--diagnostic-core-timing', str(timing)))
                    if arm == 'trial':
                        command.extend(('--diagnostic-joint-rapid-release', str(support)))
                    checkpoint(stem)
                    with snapshot.open('x') as stdout, stderr.open('x') as err:
                        subprocess.run(command, stdout=stdout, stderr=err, timeout=900, check=True)
                    measured = read_replay(snapshot)
                    row = dict(command=command, snapshot_sha256=digest(snapshot), output=measured['output'])
                    dataset['runs'][stem] = row
                    if arm == 'trial':
                        row['mechanism'] = parse_counters(stderr.read_text())
                    if not timed:
                        if arm == 'current':
                            check_identity(snapshot, midi, pin)
                            dataset['saved_current_identity'] = True
                        base_snapshot = measured
                        with snapshot.open() as stream:
                            aggregate = next(csv.DictReader(stream, delimiter='\t'))
                        if int(aggregate['samples']) != count or int(aggregate['sample_rate']) != RATE:
                            raise ValueError('Replay clock differs')
                        events = read_events(midi, sample_count=count,
                                             transition_count=int(aggregate['transitions']))
                        lifecycle = summarize(events, measured['labels'], sample_count=count,
                            sample_rate=RATE, include_output_safety=True)
                        spans, audit = native_spans(events, sample_count=count, sample_rate=RATE)
                        dataset['arms'][arm] = dict(snapshot=measured, lifecycle=lifecycle,
                            pitch=score(spans, measured['labels'], sample_count=count, sample_rate=RATE),
                            conflicts=raw_conflicts(events), raw_audit=audit)
                        row.update(midi_sha256=digest(midi), raw_audit=audit)
                        save(bulk / (stem + '-spans.json'), spans)
                    else:
                        row['buffer_identity'] = measured == base_snapshot
                        row['timing'] = json.loads(timing.read_text())
                        row['timing_gates'] = timing_gates(row['timing'], measured, block)
                # Timing companions must not change diagnostic accounting either.
                if arm == 'trial':
                    canonical = dataset['runs'][f'{name}-trial-512']['mechanism']
                    dataset['mechanism_buffer_identity'] = all(
                        row['mechanism'] == canonical for key, row in dataset['runs'].items()
                        if '-trial-' in key)
            dataset['comparison'] = evaluate(dataset['arms']['current'], dataset['arms']['trial'])
            dataset['processing_pass'] = all(
                row['buffer_identity'] and row['timing_gates']['timed_scored_identity']
                and row['timing_gates']['zero_processing_allocations']
                and row['timing_gates']['timing_pass'] is not False
                for row in dataset['runs'].values() if 'timing_gates' in row)
            checkpoint(name + ' scored')
        utility = report['datasets']['ordinary']['comparison']['gap_reduction_fraction']
        report['utility_pass'] = utility is not None and utility >= .20
        passed = report['utility_pass'] and all(
            data['saved_current_identity'] and data['processing_pass'] and data['mechanism_buffer_identity']
            and all(data['comparison']['gates'].values()) for data in report['datasets'].values())
        report.update(state='completed', final=True, screen_accepted=passed,
                      verdict='accepted offline screen' if passed else 'rejected')
        checkpoint('final; installed output unchanged')
    except Exception as error:
        report.update(state='failed', final=True, error=repr(error))
        checkpoint(report.get('stage', 'initialization'))
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('binary', 'corpus', 'manifest', 'spec', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    args.binary, args.corpus, args.output = args.binary.resolve(), args.corpus.resolve(), args.output.resolve()
    run(args)


if __name__ == '__main__':
    main()
