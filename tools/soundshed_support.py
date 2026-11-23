"""One frozen saved-span support test. No audio, model, native or remote execution."""
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement
from tools.fretnet_comparison import label_budget
from tools.native_neural_consensus import intersect_spans
from tools.pitch_detector_comparison import compare, score, union_spans
from tools.soundshed_comparison import read_events


PINS = {
    'docs/recovery/basic-pitch-baseline-20261121.json':
        'da173e1940fb99a0057b7406ea4b8453df10bc4ee571d5e7d1708b25222172f1',
    'build/recovery/m3-native-neural-consensus-20261121/report.json':
        '6a80b45e7f7ba5a3732e471cb825fa6474297938a5a24661dc23792b6dc34d06',
    'build/recovery/m3-native-neural-consensus-20261121/ordinary-consensus-spans.json.gz':
        '0d0dc2973a0dc3e4c4392b62706887bfae1f7cc36b9054c3714aed816022f2a3',
    'build/recovery/m3-native-neural-consensus-20261121/extended-middle-consensus-spans.json.gz':
        'da09fbe6fc18c1ad54d7b3a926e9bc95a06361c3e47b1ff13e18cf99ec3fb21d',
    'build/github-results/soundshed-comparison-45218379585/report/soundshed-result/report/report.json':
        '0d1962b8ad8653e5d8949bf8c5b726ec07e0a530874bc58a3c7d002687e7bfde',
}
BASELINE = 'docs/recovery/basic-pitch-baseline-20261121.json'
CONSENSUS = 'build/recovery/m3-native-neural-consensus-20261121'
SOUNDSHED = 'build/github-results/soundshed-comparison-45218379585'
REPORT = SOUNDSHED + '/report/soundshed-result/report/report.json'
HORIZONS = {'ordinary': 10681922, 'extended-middle': 2233574}
HOLD_MS = 220
LOW, HIGH = 35, 88


def canonical(value):
    return json.loads(json.dumps(value))


def load_pinned(root, name, expected=None):
    raw = (root / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != (expected or PINS[name]):
        raise ValueError('Input hash differs: ' + name)
    return json.loads(gzip.decompress(raw) if name.endswith('.gz') else raw)


def filter_spans(current, model, native, *, sample_count, sample_rate):
    """Forward-only support; model's unsupported pitches always retain CURRENT."""
    if type(sample_rate) is not int or sample_rate <= 0:
        raise ValueError('Positive integer sample rate required')
    current = union_spans(current, sample_count=sample_count)
    support = union_spans([*model, *native], sample_count=sample_count)
    hold = HOLD_MS * sample_rate // 1000
    held = union_spans([(a, min(b + hold, sample_count), n) for a, b, n in support],
                       sample_count=sample_count)
    supported = intersect_spans([s for s in current if LOW <= s[2] <= HIGH], held,
                                sample_count=sample_count)
    return union_spans([*[s for s in current if not LOW <= s[2] <= HIGH], *supported],
                       sample_count=sample_count)


def compact(measured):
    p = measured['pitch_sets']
    t = p['totals']
    false = t['extra_pitch_voice_samples'] + p['unlabeled_gap_voice_samples']
    return dict(present=t['present_pitch_samples'], expected=t['expected_pitch_samples'],
        coverage_pct=100 * t['present_pitch_samples'] / t['expected_pitch_samples'],
        wrong=t['extra_pitch_voice_samples'], gap=p['unlabeled_gap_voice_samples'],
        precision_pct=100 * t['present_pitch_samples'] / (t['present_pitch_samples'] + false),
        exact_set=t['exact_pitch_set_samples'], all_expected=t['all_expected_pitches_samples'])


def delay_deltas(current, measured):
    rows = []
    for before, after in zip(current['labels'], measured['labels'], strict=True):
        if (before['label_index'], before['midi_note']) != (after['label_index'], after['midi_note']):
            raise ValueError('Delay rows are not aligned')
        a, b = before['first_present_delay_samples'], after['first_present_delay_samples']
        rows.append(dict(label_index=before['label_index'], midi_note=before['midi_note'],
            current_first_present_delay_samples=a, candidate_first_present_delay_samples=b,
            delay_delta_samples=None if a is None or b is None else b-a))
    return rows


def utility_gate(rows):
    ordinary = rows['ordinary']
    before, after = ordinary['current_summary'], ordinary['candidate_summary']
    checks = dict(
        ordinary_wrong_reduction_20pct=(before['wrong'] - after['wrong']) * 100 >= 20 * before['wrong'],
        ordinary_gap_reduction_250000=after['gap'] - before['gap'] <= -250000,
        ordinary_coverage_loss_010pp=(before['present'] - after['present']) * 1000 <= before['expected'],
        extended_middle_strict=rows['extended-middle']['budget']['strict_screen_pass'],
        both_label_budgets=all(r['budget']['budget_screen_pass'] for r in rows.values()))
    return dict(checks=checks, passed=all(checks.values()), promotion_accepted=False)


def run(root, event_dir, output):
    if output.exists():
        raise FileExistsError('Result exists; no repeat scoring: ' + str(output))
    baseline = load_pinned(root, BASELINE)['datasets']
    consensus = load_pinned(root, CONSENSUS + '/report.json')['datasets']
    source = load_pinned(root, REPORT)['datasets']
    rows, provenance = {}, dict(PINS)
    for name, horizon in HORIZONS.items():
        base, reference, saved = baseline[name], consensus[name], source[name]
        full = dict(sample_count=base['measurement']['sample_count'],
                    sample_rate=base['measurement']['sample_rate'])
        if full['sample_rate'] != 96000 or reference['common_support']['sample_count'] != horizon:
            raise ValueError('Frozen recording clock differs')
        labels = labels_from_measurement(base['measurement'])
        if canonical(score(base['pitch_spans'], labels, **full)) != base['measurement']:
            raise ValueError('Full CURRENT identity failed: ' + name)
        event_path = event_dir / (name + '-events.tsv')
        digest = hashlib.sha256(event_path.read_bytes()).hexdigest()
        if digest != saved['bulk'][event_path.name]['sha256']:
            raise ValueError('Causal event hash differs: ' + name)
        provenance[str(event_path.relative_to(root))] = digest
        model, audit = read_events(event_path, **full)
        if not audit['pairing_valid'] or audit != saved['event_audit']:
            raise ValueError('Causal event accounting differs: ' + name)
        if canonical(score(model, labels, **full)) != saved['arms']['soundshed']['measurement']:
            raise ValueError('Soundshed event-to-score identity failed: ' + name)
        clipped_labels, clipping = clip_labels(labels, horizon)
        if len(clipped_labels) != len(labels) or any(a != b for a, b in zip(labels, clipped_labels)):
            raise ValueError('Common horizon removed annotation samples: ' + name)
        clock = dict(sample_count=horizon, sample_rate=full['sample_rate'])
        current_spans = clip_spans(base['pitch_spans'], horizon)
        current = score(current_spans, clipped_labels, **clock)
        if canonical(current) != reference['current']:
            raise ValueError('Common CURRENT identity failed: ' + name)
        native = load_pinned(root, CONSENSUS + '/' + name + '-consensus-spans.json.gz')['native_confirmation']
        candidate_spans = filter_spans(current_spans, clip_spans(model, horizon), native, **clock)
        measured = score(candidate_spans, clipped_labels, **clock)
        comparison = compare(current, measured)
        rows[name] = dict(clock=clock, full_recording_clock=full,
            integrity=dict(full_current_identity=True, common_current_identity=True,
                soundshed_identity=True, causal_pairing=True, annotations_unchanged=True),
            current_summary=compact(current), candidate_summary=compact(measured),
            current_pitch_runs=len(union_spans(current_spans, sample_count=horizon)),
            candidate_pitch_runs=len(candidate_spans),
            comparison=comparison, budget=label_budget(comparison, full['sample_rate']),
            first_present_delay_deltas=delay_deltas(current, measured),
            measurement=measured, candidate_spans=candidate_spans,
            soundshed_timing=saved['timing'])
    screen = utility_gate(rows)
    result = dict(schema='m3_soundshed_support_v1', final=True,
        completed_at=datetime.now(timezone.utc).isoformat(), provenance=provenance,
        hold_ms=HOLD_MS, supported_range=[LOW, HIGH], datasets=rows, screen=screen,
        verdict='PASS_SAVED_SPAN_DESIGN_SCREEN' if screen['passed'] else 'REJECTED_SAVED_SPAN_SUPPORT',
        installed_output_changed=False, promotion_accepted=False,
        limitations='Design recordings, pitch occupancy only; no causal joint MIDI implementation, '
            'string/unison or acoustic re-pluck verification. Soundshed timing already fails M3 '
            'limits; joint runtime, allocations, host/hardware and live readiness unmeasured.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(verdict=result['verdict'], screen=screen, datasets={k:
        {n: v[n] for n in ('current_summary', 'candidate_summary', 'current_pitch_runs',
                           'candidate_pitch_runs', 'budget')} for k, v in rows.items()}), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(Path(__file__).resolve().parents[1], args.events.resolve(), args.out.resolve())
