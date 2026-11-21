"""Bounded GitHub-only source verification. No model, relabeling or replay."""
import argparse
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import time

import numpy as np
import scipy

from tools.direct_spectrum_learning import validate_manifest
from tools.pitch_detector_comparison import digest
from tools.portable_basic_pitch_cached_diagnosis import require_identity
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.portable_direct_spectrum_learning import fetch_release, source_waves
from tools.portable_source_pitch_diagnostic import verify_expected_cents
from tools.source_pitch_verification import PARAMETERS, measure_take, select_sources, source_context


def run(spec_path, output):
    remote_only()
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report','logs','cache','inputs','bulk')}
    for folder in folders.values():
        folder.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_source_pitch_verification_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), installed_output_changed=False,
        labels_changed=False, exclusions=0, fits=0, live_readiness='not measured')
    try:
        spec = json.loads(spec_path.read_text())
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git','-C',str(root),'rev-parse','HEAD'])
        if (source != os.environ.get('SOURCE_SHA')
                or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']
                or np.__version__ != '1.26.4' or scipy.__version__ != '1.13.1'):
            raise ValueError('Frozen execution provenance mismatch')
        require_identity(spec['parameters'], PARAMETERS, 'parameters')
        for name, pin in spec['unchanged_files'].items():
            check_hash(root/name, pin)
        pin = spec['sources']
        check_hash(root/pin['path'], pin['sha256'])
        manifest = json.loads((root/pin['path']).read_text())
        takes, counts = validate_manifest(manifest)
        require_identity(counts, dict(train=200, calibration=200, test=155), 'source roles')
        pin = spec['selection_basis']
        check_hash(root/pin['path'], pin['sha256'])
        basis = json.loads((root/pin['path']).read_text())
        selection = select_sources(basis['sources'])
        require_identity(selection, spec['selection'], 'fixed all-other takes and agreeing controls')
        by_key = {row['key']: row for row in takes}
        if {r['source_key'] for r in basis['sources']} != set(by_key):
            raise ValueError('Selection basis does not contain every source')
        for row in basis['sources']:
            take = by_key[row['source_key']]
            if (row['role'], row['note'], row['string_mask']) != (take['role'], take['midi_note'], take['string_mask']):
                raise ValueError('Selection basis metadata differs')
        if selection['flagged_count'] != 15 or selection['unique_control_count'] != 25:
            raise ValueError('Frozen selection count differs')
        selected = [by_key[key] for key in selection['source_keys']]
        report['provenance'] = dict(source_commit=source, worker_commit=os.environ['GITHUB_SHA'],
            run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
            specification=spec, specification_sha256=digest(spec_path))
        report['stage'] = 'retrieve existing pinned source recordings'
        save_json(report_path, report)
        report['inputs'] = [fetch_release(spec['worker_repository'], pin, folders['cache'],
            folders['inputs'], folders['logs']) for pin in spec['input_releases']]
        cents_count = verify_expected_cents(manifest, folders['inputs'])
        stems = {take['stem'] for take in selected}
        waves = source_waves(dict(manifest, files=[f for f in manifest['files'] if f['stem'] in stems]),
                             folders['inputs'])
        report['integrity'] = dict(source_roles=counts, selection_reproduced=True,
            source_takes=len(takes), expected_cents_rows_verified=cents_count,
            selected_takes=len(selected), loaded_strings=sorted(stems))
        report['stage'] = 'systematic full-take trajectories and harmonic spectra'
        save_json(report_path, report)
        evidence = folders['bulk']/'source-verification.jsonl.gz'
        report['takes'] = []
        started = time.perf_counter()
        with gzip.open(evidence, 'wt', encoding='utf-8') as stream:
            for take in selected:
                waveform = waves[take['stem']][take['start_sample']:take['end_sample']]
                summary, rows = measure_take(waveform, take, source_context(take, takes))
                report['takes'].append(summary)
                for row in rows:
                    stream.write(json.dumps(row, separators=(',',':'), allow_nan=False)+'\n')
                print(f"measured {take['key']}: {len(rows)} systematic windows", flush=True)
        report['measurement_seconds'] = time.perf_counter()-started
        report['evidence'] = {evidence.name: dict(bytes=evidence.stat().st_size, sha256=digest(evidence))}
        report['limits'] = spec['limits']
        report.update(state='completed', final=True,
            decision='Source observations only; labels, held-out scores and installed output unchanged.',
            stage='all 15 flagged takes and 25 agreeing controls measured')
    except BaseException as error:
        report.update(state='failed', error=repr(error), final=True)
        raise
    finally:
        report['finished_or_updated_at'] = datetime.now(timezone.utc).isoformat()
        save_json(report_path, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.spec, args.output)
    print(json.dumps(dict(state=result['state'], takes=len(result['takes']))))
