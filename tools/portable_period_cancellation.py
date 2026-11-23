"""One fixed period-cancellation screen; recorded inputs run on GitHub CPU only."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

import numpy as np

from tools.direct_spectrum_learning import mixture_plan, validate_manifest
from tools.paired_component_mixture import paired_audio
from tools.period_cancellation import (ARMS, SETTINGS, PartialReadout,
    calibrate_cutoff, decision, mixture_queries, summarize_queries)
from tools.pitch_detector_comparison import digest
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.portable_direct_spectrum_learning import fetch_release, save_gzip_json, source_waves


ROLES = ('train', 'calibration', 'test')


def measure_role(role, takes, waves, readout, bulk):
    remote_only()
    started = time.perf_counter()
    plan = mixture_plan(takes, role=role, count=SETTINGS['examples_per_role'],
                        seed=SETTINGS['seeds'][role])
    save_gzip_json(bulk/(role+'-mixture-plan.json.gz'), plan)
    counts = Counter(c['source_key'] for row in plan for c in row['components'])
    expected = {take['key'] for take in takes if take['role'] == role}
    if set(counts) != expected:
        raise ValueError('Source role omitted or crossed: '+role)
    queries, row_integrity = [], []
    max_recomposition, max_linearity = 0., 0.
    silence_scores = {arm: 0. for arm in ARMS}
    silence_rows = 0
    for index, row in enumerate(plan):
        mixed, targets, components, error = paired_audio(row, waves)
        actual, checks = mixture_queries(row, mixed, components, readout)
        # The existing generator's target map must equal the distinct query set.
        if [r['note'] for r in actual] != (np.flatnonzero(targets)+SETTINGS['note_low']).tolist():
            raise ValueError('Intended query coverage differs')
        queries.extend(actual)
        max_recomposition = max(max_recomposition, error, checks['recomposition_error'])
        max_linearity = max(max_linearity, checks['linearity_error'])
        if checks['silence_maximum_score'] is not None:
            silence_rows += 1
            for arm in ARMS:
                silence_scores[arm] = max(silence_scores[arm], checks['silence_maximum_score'][arm])
        row_integrity.append(dict(example=row['example'], **checks))
        if (index+1) % 128 == 0:
            print(json.dumps(dict(role=role, mixtures=index+1, queries=len(queries))), flush=True)
    save_gzip_json(bulk/(role+'-queries.json.gz'), queries)
    save_gzip_json(bulk/(role+'-integrity.json.gz'), row_integrity)
    integrity = dict(all_sources_retained=True, all_distinct_pitch_queries_present=True,
        recomposition=max_recomposition <= SETTINGS['identity_tolerance'],
        filter_linearity=max_linearity <= SETTINGS['identity_tolerance'],
        silence_retained=silence_rows == sum(not row['components'] for row in plan) and silence_rows > 0)
    info = dict(examples=len(plan), queries=len(queries), source_take_uses=dict(counts),
        silence_rows=silence_rows, silence_maximum_score=silence_scores,
        max_recomposition_error=max_recomposition, max_filter_linearity_error=max_linearity,
        integrity=integrity, seconds=time.perf_counter()-started)
    if not all(integrity.values()):
        raise ValueError('Role integrity failed: '+role)
    return queries, info


def run(spec_path, output):
    remote_only()  # Before files, recorded data, downloads or dependency checks.
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache', 'inputs', 'bulk')}
    for folder in folders.values():
        folder.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_period_cancellation_result_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), installed_output_changed=False,
        promotion_accepted=False, fits=0, labels_changed=False, roles={})
    try:
        import soundfile
        spec = json.loads(spec_path.read_text())
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git', '-C', str(root), 'rev-parse', 'HEAD'])
        if (source != os.environ.get('SOURCE_SHA')
                or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']
                or np.__version__ != '1.26.4' or soundfile.__version__ != '0.13.1'):
            raise ValueError('Frozen execution provenance mismatch')
        if spec['settings'] != SETTINGS or spec['arms'] != list(ARMS):
            raise ValueError('Frozen settings or arms differ')
        report['provenance'] = dict(source_sha=source, worker_sha=os.environ['GITHUB_SHA'],
            run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
            specification=spec, specification_sha256=digest(spec_path),
            numpy=np.__version__, soundfile=soundfile.__version__)
        source_path = root/spec['sources']['path']
        check_hash(source_path, spec['sources']['sha256'])
        manifest = json.loads(source_path.read_text())
        takes, counts = validate_manifest(manifest)
        if counts != dict(train=200, calibration=200, test=155):
            raise ValueError('Source role counts differ')
        report['source_roles'] = dict(counts=counts, original_cross_role_overlap=False,
            all_takes_retained=True, fresh_external_validation=False)
        report['stage'] = 'retrieve existing pinned releases'
        save_json(report_path, report)
        report['inputs'] = [fetch_release(spec['worker_repository'], pin, folders['cache'],
                            folders['inputs'], folders['logs']) for pin in spec['input_releases']]
        waves = source_waves(manifest, folders['inputs'])
        readout, saved_queries, cutoffs = PartialReadout(), {}, None
        for role in ROLES:
            report['stage'] = 'fixed period cancellation and matched negatives: '+role
            save_json(report_path, report)
            queries, info = measure_role(role, takes, waves, readout, folders['bulk'])
            saved_queries[role] = queries
            report['roles'][role] = info
            if role == 'calibration':
                cutoffs = {arm: calibrate_cutoff([q['arms'][arm]['absent_score'] for q in queries])
                           for arm in ARMS}
                # This write occurs BEFORE any test mixture is rendered/measured.
                save_json(folders['bulk']/'frozen-cutoffs.json', cutoffs)
                report['cutoffs'] = dict(arms=cutoffs, source='calibration matched negatives only',
                    positives_used=False, test_used=False, persisted_before_test=True,
                    sha256=digest(folders['bulk']/'frozen-cutoffs.json'))
            if cutoffs is not None:
                for measured_role in saved_queries:
                    if 'summary' not in report['roles'][measured_role]:
                        report['roles'][measured_role]['summary'] = summarize_queries(saved_queries[measured_role], cutoffs)
            save_json(report_path, report)
        integrity = dict(source_counts=True, pinned_input_identity=True, fixed_settings=True,
            calibration_before_test=report['cutoffs']['persisted_before_test'],
            all_role_integrity=all(all(info['integrity'].values()) for info in report['roles'].values()),
            calibration_false_cap=all(c['observed_false'] <= c['allowed_false'] for c in cutoffs.values()))
        test = report['roles']['test']
        report['integrity'] = integrity
        report['primary_decision'] = decision(test['summary'], all(integrity.values()),
            test['silence_maximum_score'], cutoffs)
        report['oracle_diagnostic_decision'] = decision(test['summary'], all(integrity.values()),
            test['silence_maximum_score'], cutoffs, arm='component_period_oracle')
        report.update(state='completed', final=True, stage='fixed mechanism screen complete',
            decision=report['primary_decision']['verdict'],
            limits=['Matched synthetic negatives and source-pass roles are reused design data.',
                'All intended labels retained, including known target-pitch uncertainty.',
                'No native detector, string assignment, unison multiplicity or delivered MIDI test.',
                'No continuous real-chord, allocation, deadline, host or live-device acceptance.',
                'Oracle source selection is diagnostic only; raw plus residual integration is not built.',
                'No retuning, repeated rejected screen, installed change or promotion.'])
        report['evidence'] = {p.name: dict(bytes=p.stat().st_size, sha256=digest(p))
                              for p in folders['bulk'].iterdir() if p.is_file()}
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_or_updated_at'] = datetime.now(timezone.utc).isoformat()
        save_json(report_path, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', dest='spec_path', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    result = run(**vars(parser.parse_args()))
    print(json.dumps(dict(state=result['state'], decision=result['decision'])))
