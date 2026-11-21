"""Saved-stream consensus on the source-sample clock; no audio or model execution.

Native confirmation is exposed at the next aligned callback boundary. A missing
callback observation supplies no confirmation. This does not measure the joint
runtime cost of the two detectors or implement a string/MIDI ownership policy.
"""
from collections import defaultdict
import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement
from tools.candidate_outcome_analysis import _candidates
from tools.pitch_detector_comparison import compare, digest, score, union_spans


TRACE_PINS = {
    'ordinary': {
        'path': 'build/github-results/unfiltered-observation-44835727027/evidence/github-results/unfiltered-observation/ordinary-current-on-512-outcome-v5.tsv.gz',
        'sha256': 'cd905b2f5c2d9e9ff0d898c87c893fe3f79ca6b388c685dd052256d421879541',
        'raw_sha256': 'b664c7ff0ce80bd4e544b647ce48688ecf181918cb7e36643370bab2eccfbd93',
        'run_id': 44835727027,
        'source_commit': '0b3fcbad7ab349c25a8ec1705f2216ce0d1271b0',
        'raw_midi_sha256': '77e52ee4b498c3c1656edd3c747934efc55b2a71a7e0ee63ba9cbd232feb613a',
    },
    'extended-middle': {
        'path': 'build/github-results/qualified-tier-retention-corpus-43736868711/saved-extended-middle/extended-middle-current-on-512-outcome.tsv.gz',
        'sha256': '82781c2db888e66c2de3acda0bc904701299891f40a5d56a1bbe2ca000e0a269',
        'raw_sha256': '04f0a2c56fdb7713653181b1ba70981044824df9b6b515afa7cb9ebb97e1aa65',
        'run_id': 43736868711,
        'source_commit': 'fb1c4b8c0edccd460f5ba9bea1c2963997d07206',
        'raw_midi_sha256': 'a52eb7d46ae0fd7345e97e5652c29a367b8bfc45bf0db4803eba304bcc8ec601',
    },
}
BRIDGE_PATH = 'build/github-results/basic-pitch-cached-44891340815/basic-pitch-cached-result/report/report.json'
BRIDGE_SHA256 = 'da1ba0a1e2aa0bd0df9b9db07a12344d24c683a793545e60c84d2ac4a2aec773'
EVIDENCE_DIR = 'build/github-results/basic-pitch-cached-44891340815/claude-event-evidence/files'
BASELINE_PATH = 'docs/recovery/basic-pitch-baseline-20261121.json'


def selector_confirmation(candidate):
    """Direct pitch offered to the selector, including a DP-evicted option.

    This is not final selection or a claim about generic raw admission: grouped
    unisons have their own pool insertion path. No new energy cut is introduced.
    """
    for key in ('selector_pool_member', 'direct'):
        if candidate.get(key) not in (0, 1):
            raise ValueError('Missing or invalid native selector/direct flag')
    return candidate['selector_pool_member'] == 1 and candidate['direct'] == 1


def confirmation_spans(observations, *, sample_count, block_size=512):
    """Use the latest observed native state per completed callback, for one block.

    Each observation is (zero-based post-sample index, set of confirmed pitches).
    An observation at sample 511 can first affect output at 512. Observations
    earlier in that same callback cannot override its last observation. Without
    another observation, support expires one callback later instead of coasting.
    """
    if type(sample_count) is not int or sample_count <= 0:
        raise ValueError('Positive integer horizon required')
    if type(block_size) is not int or block_size <= 0:
        raise ValueError('Positive integer callback size required')
    spans = []
    previous_sample = -1
    pending_boundary, pending_notes = None, set()
    observed_rows = observed_callbacks = 0

    def emit(boundary, notes):
        if boundary is not None and boundary < sample_count:
            end = min(boundary + block_size, sample_count)
            spans.extend((boundary, end, note) for note in sorted(notes))

    for sample, notes in observations:
        if type(sample) is not int or sample <= previous_sample:
            raise ValueError('Native observations must have strictly increasing samples')
        if any(type(note) is not int or not 0 <= note <= 127 for note in notes):
            raise ValueError('Invalid native confirmation pitch')
        boundary = ((sample + 1 + block_size - 1) // block_size) * block_size
        if boundary != pending_boundary:
            emit(pending_boundary, pending_notes)
            observed_callbacks += 1
            pending_boundary = boundary
        pending_notes = set(notes)
        previous_sample = sample
        observed_rows += 1
    emit(pending_boundary, pending_notes)
    if not observed_rows:
        raise ValueError('Empty native observation trace')
    return union_spans(spans, sample_count=sample_count), dict(
        observed_rows=observed_rows, observed_callbacks=observed_callbacks,
        last_observed_sample=previous_sample, block_size=block_size,
        expiry='One callback after availability; missing observations do not coast')


def intersect_spans(first, second, *, sample_count):
    """Same-pitch interval intersection, preserving both inputs' clocks."""
    grouped = []
    for spans in (first, second):
        by_pitch = defaultdict(list)
        for left, right, pitch in union_spans(spans, sample_count=sample_count):
            by_pitch[pitch].append((left, right))
        grouped.append(by_pitch)
    result = []
    for pitch in sorted(grouped[0].keys() & grouped[1].keys()):
        a, b = grouped[0][pitch], grouped[1][pitch]
        i = j = 0
        while i < len(a) and j < len(b):
            left, right = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
            if left < right:
                result.append((left, right, pitch))
            if a[i][1] < b[j][1]:
                i += 1
            else:
                j += 1
    return union_spans(result, sample_count=sample_count)


def read_trace(path, predicate, audit, expected_raw_sha256=None):
    """Read one trace pass; annotations/voices never feed the confirmation rule."""
    hasher = hashlib.sha256()
    with gzip.open(path, 'rb') as stream:
        def lines():
            for raw in stream:
                hasher.update(raw)
                yield raw.decode('utf-8')
        text_lines = lines()
        marker = next(text_lines).strip()
        if marker not in {f'# m3_candidate_outcome_v{i}' for i in range(2, 6)}:
            raise ValueError('Trace must include the native selector diagnostics')
        reader = csv.DictReader(text_lines, delimiter='\t')
        if not {'sample', 'tick', 'quiet', 'candidates'} <= set(reader.fieldnames or []):
            raise ValueError('Missing native trace columns')
        audit.update(schema=marker, rows=0, candidate_rows=0, confirmed_candidate_rows=0,
                     missing_decision_rows=0, quiet_rows=0, quiet_disposition_counts=[0] * 8)
        previous = None
        for row in reader:
            sample, tick, quiet = int(row['sample']), int(row['tick']), int(row['quiet'])
            # QuietDisposition is an eight-value enum; only zero is not_quiet.
            if not 0 <= quiet < 8 or sample < 0 or tick < 0:
                raise ValueError('Invalid native decision coordinates')
            if previous is not None:
                if sample <= previous[0] or tick <= previous[1]:
                    raise ValueError('Native trace is not strictly ordered')
                if (sample - previous[0]) % 64:
                    raise ValueError('Native trace is off its 64-sample decision grid')
                audit['missing_decision_rows'] += (sample - previous[0]) // 64 - 1
            candidates = _candidates({'candidate_text': row['candidates']})
            confirmed = {note for note, candidate in candidates.items()
                         if not quiet and predicate(candidate)}
            audit['rows'] += 1
            audit['candidate_rows'] += len(candidates)
            audit['confirmed_candidate_rows'] += len(confirmed)
            audit['quiet_rows'] += int(quiet != 0)
            audit['quiet_disposition_counts'][quiet] += 1
            if previous is None:
                audit['first_sample'], audit['first_tick'] = sample, tick
            audit['last_sample'], audit['last_tick'] = sample, tick
            previous = sample, tick
            yield sample, confirmed
    audit['raw_sha256'] = hasher.hexdigest()
    if expected_raw_sha256 is not None and audit['raw_sha256'] != expected_raw_sha256:
        raise ValueError('Native trace payload differs from its producing report pin')


def load_json(path):
    with Path(path).open(encoding='utf-8') as stream:
        return json.load(stream)


def compact(measurement):
    totals = measurement['pitch_sets']['totals']
    return dict(
        expected_pitch_samples=totals['expected_pitch_samples'],
        present_pitch_samples=totals['present_pitch_samples'],
        present_percent=100 * totals['present_pitch_samples'] / totals['expected_pitch_samples'],
        wrong_pitch_samples=totals['extra_pitch_voice_samples'],
        gap_extra_pitch_samples=measurement['pitch_sets']['unlabeled_gap_voice_samples'],
        exact_pitch_set_samples=totals['exact_pitch_set_samples'],
        all_expected_samples=totals['all_expected_pitches_samples'])


def run(repo, output):
    """One fixed saved-data screen. Refuse to overwrite an earlier execution."""
    repo, output = Path(repo), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_native_neural_consensus_v1', state='running', final=False,
                  started_at=datetime.now(timezone.utc).isoformat(), datasets={},
                  predicate='not quiet and selector_pool_member == 1 and direct == 1',
                  projection_block_samples=512, neural_arm='A',
                  fusion='CURRENT union (measured FIFO Basic Pitch intersection native confirmation)',
                  installed_output_changed=False, promotion_accepted=False,
                  inference_performed=False, native_execution_performed=False,
                  clock_limit='Native confirmation projected to completed aligned 512-sample callbacks; joint runtime unmeasured',
                  trace_limit='Fail closed: legacy inclusion filters may omit eligible candidate rows',
                  measurement_limit='Distinct-pitch occupancy; no lane, unison multiplicity or delivered-host MIDI claim')
    report_path = output / 'report.json'
    try:
        if digest(repo / BRIDGE_PATH) != BRIDGE_SHA256:
            raise ValueError('Bridge report differs from frozen hash')
        bridge, baseline = load_json(repo / BRIDGE_PATH), load_json(repo / BASELINE_PATH)
        report['provenance'] = dict(bridge_run=44891340815, bridge_sha256=BRIDGE_SHA256,
                                    baseline_sha256=digest(repo / BASELINE_PATH),
                                    implementation_sha256=digest(Path(__file__)))
        for name, pin in TRACE_PINS.items():
            data, base = bridge['datasets'][name], baseline['datasets'][name]
            for key in ('raw_midi_sha256', 'source_commit', 'run_id'):
                if str(base[key]) != str(pin[key]):
                    raise ValueError(f'{name}: native baseline provenance differs ({key})')
            trace = repo / pin['path']
            if digest(trace) != pin['sha256']:
                raise ValueError(name + ': trace differs from frozen hash')
            horizon = data['common_support']['sample_count']
            rate = data['common_support']['sample_rate']
            clock = dict(sample_count=horizon, sample_rate=rate)
            labels, clipping = clip_labels(labels_from_measurement(base['measurement']), horizon)
            current_spans = clip_spans(base['pitch_spans'], horizon)
            current = score(current_spans, labels, **clock)
            if current != data['current_measurement']:
                raise ValueError(name + ': CURRENT identity failed')
            evidence_pin = data['evidence']
            evidence_path = repo / EVIDENCE_DIR / evidence_pin['name']
            if (evidence_path.stat().st_size != evidence_pin['bytes']
                    or digest(evidence_path) != evidence_pin['sha256']):
                raise ValueError(name + ': event evidence differs from bridge pin')
            with gzip.open(evidence_path, 'rt', encoding='utf-8') as stream:
                evidence = json.load(stream)
            if evidence['common_horizon'] != horizon:
                raise ValueError(name + ': event horizon differs')
            neural_spans = evidence['arm_spans']['A']
            neural = score(neural_spans, labels, **clock)
            if neural != data['measurements']['A']:
                raise ValueError(name + ': measured FIFO arm identity failed')
            audit = {}
            confirmations, projection = confirmation_spans(
                read_trace(trace, selector_confirmation, audit, pin['raw_sha256']), sample_count=horizon)
            additions = intersect_spans(neural_spans, confirmations, sample_count=horizon)
            hybrid_spans = union_spans([*current_spans, *additions], sample_count=horizon)
            hybrid = score(hybrid_spans, labels, **clock)
            comparison = compare(current, hybrid)
            label_deltas = comparison['label_deltas']
            preserve = all(row['present_samples_delta'] >= 0 and row['longest_present_samples_delta'] >= 0
                           for row in label_deltas)
            if not preserve:
                raise ValueError(name + ': union failed per-label CURRENT preservation')
            spans_path = output / (name + '-consensus-spans.json.gz')
            with spans_path.open('wb') as raw:
                with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as archive:
                    archive.write(json.dumps(dict(common_horizon=horizon,
                        native_confirmation=confirmations, confirmed_neural=additions,
                        hybrid=hybrid_spans), separators=(',', ':')).encode('utf-8'))
            row = dict(trace_pin=pin, trace=audit, projection=projection,
                       common_support=data['common_support'], label_clipping=clipping,
                       current_identity=True, neural_A_identity=True,
                       current_raw_event_audit=base['audit'], neural_A_raw_event_audit=data['event_audits']['A'],
                       current=current, neural_A=neural, hybrid=hybrid, comparison=comparison,
                       compact={key: compact(value) for key, value in
                                [('CURRENT', current), ('A', neural), ('hybrid', hybrid)]},
                       pitch_occupancy_segments=dict(current=len(union_spans(current_spans, sample_count=horizon)),
                                                     hybrid=len(hybrid_spans), confirmed_neural=len(additions)),
                       all_current_label_presence_and_longest_preserved=preserve,
                       spans_evidence=dict(name=spans_path.name, bytes=spans_path.stat().st_size,
                                           sha256=digest(spans_path)))
            report['datasets'][name] = row
            report_path.write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(dict(dataset=name, compact=row['compact'],
                                  no_pitch_safety_regression=comparison['no_pitch_safety_regression'])), flush=True)
        safe = all(row['comparison']['no_pitch_safety_regression'] for row in report['datasets'].values())
        gain = report['datasets']['ordinary']['comparison']['sample_deltas']['present_pitch_samples'] > 0
        report.update(state='completed', final=True, screen_passed=safe and gain,
                      verdict='passes saved-data screen only' if safe and gain else 'rejected',
                      acceptance=dict(both_datasets_no_pitch_safety_regression=safe,
                                      ordinary_present_gain=gain))
    except Exception as exc:
        report.update(state='failed', final=True, error=str(exc))
        raise
    finally:
        report['finished_or_updated_at'] = datetime.now(timezone.utc).isoformat()
        report_path.write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.repo, args.output)
    print(json.dumps(dict(verdict=report['verdict'], output=str(args.output / 'report.json'))))


if __name__ == '__main__':
    main()
