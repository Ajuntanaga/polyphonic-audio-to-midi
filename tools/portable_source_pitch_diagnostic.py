"""One observation-only source-crop check on GitHub CPU; never fit or relabel."""
import argparse
import csv
from datetime import datetime, timezone
import gzip
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

import numpy as np
import scipy

from tools.direct_spectrum_learning import SETTINGS, mixture_plan, validate_manifest
from tools.pitch_detector_comparison import digest
from tools.portable_basic_pitch_cached_diagnosis import fetch_artifact, require_identity
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.portable_direct_spectrum_learning import fetch_release, source_waves
from tools.source_pitch_diagnostic import PARAMETERS, crop_inventory, diagnose_crop, summarize
from tools.spectral_dictionary import template_plan


def verify_expected_cents(manifest, inputs):
    """Check the calibration field omitted by the shared waveform loader."""
    remote_only()
    count = 0
    for source in manifest['files']:
        labels = inputs/source['labels_path']
        check_hash(labels, source['labels_sha256'])
        with labels.open(newline='') as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        if len(rows) != len(source['takes']):
            raise ValueError('Source label count differs')
        for row, take in zip(rows, source['takes']):
            cents = float(row['expected_cents'])
            if not math.isfinite(cents) or cents != take['expected_cents']:
                raise ValueError('Source expected_cents differs')
            count += 1
    return count


def run(spec_path, output):
    remote_only()  # Before downloads, output creation or recorded input.
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report','logs','cache','inputs','bulk')}
    for folder in folders.values():
        folder.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_source_pitch_diagnostic_v1', state='running', final=False,
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
        require_identity(spec['parameters'], PARAMETERS, 'diagnostic parameters')
        require_identity(spec['mixture_settings'], SETTINGS, 'unchanged mixture settings')
        for name, pin in spec['generator_files'].items():
            check_hash(root/name, pin['sha256'])
        pin = spec['sources']
        check_hash(root/pin['path'], pin['sha256'])
        manifest = json.loads((root/pin['path']).read_text())
        takes, counts = validate_manifest(manifest)
        require_identity(counts, dict(train=200, calibration=200, test=155), 'source roles')
        report['provenance'] = dict(source_commit=source, worker_commit=os.environ['GITHUB_SHA'],
            run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
            specification=spec, specification_sha256=digest(spec_path), python=sys.version,
            platform=platform.platform(), numpy=np.__version__, scipy=scipy.__version__)
        report['stage'] = 'retrieve and reproduce exact saved component plans'
        save_json(report_path, report)
        plan_directory = folders['cache']/'plans'
        report['saved_plan_artifact'] = fetch_artifact(spec['worker_repository'],
            spec['saved_plan_artifact'], plan_directory, folders['logs'])
        plans = {}
        for role in ('train','calibration','test'):
            with gzip.open(plan_directory/(role+'-mixture-plan.json.gz'), 'rt') as stream:
                plans[role] = json.load(stream)
            generated = mixture_plan(takes, role=role, count=SETTINGS[role+'_examples'],
                                     seed=SETTINGS[role+'_seed'])
            require_identity(plans[role], generated, role+' saved full component plan')
        with gzip.open(plan_directory/'template-plan.json.gz','rt') as stream:
            templates = json.load(stream)
        require_identity(templates, json.loads(json.dumps(template_plan(takes))),
                         'saved full template plan')
        inventory = crop_inventory(takes, plans, templates)
        report['integrity'] = dict(saved_plans_reproduced=4, source_takes=len(takes),
            source_roles=counts, unique_crops=len(inventory),
            component_exposures=sum(row['mixture_exposures'] for row in inventory),
            template_exposures=sum(row['template_exposures'] for row in inventory))
        report['stage'] = 'retrieve existing pinned source recordings'
        save_json(report_path, report)
        report['inputs'] = [fetch_release(spec['worker_repository'], pin, folders['cache'],
            folders['inputs'], folders['logs']) for pin in spec['input_releases']]
        report['integrity']['expected_cents_rows_verified'] = verify_expected_cents(
            manifest, folders['inputs'])
        waves = source_waves(manifest, folders['inputs'])
        report['stage'] = 'measure exact source crops; no mixtures, model, replay or relabeling'
        save_json(report_path, report)
        started = time.perf_counter()
        rows = []
        evidence_path = folders['bulk']/'source-crops.jsonl.gz'
        with gzip.open(evidence_path, 'wt', encoding='utf-8') as stream:
            for index, row in enumerate(inventory):
                crop = waves[row['stem']][row['crop_begin']:row['crop_end']]
                measured = dict(row, **diagnose_crop(crop, row['note'], row['expected_cents']))
                rows.append(measured)
                stream.write(json.dumps(measured, separators=(',',':'), allow_nan=False)+'\n')
                if (index+1) % 5000 == 0:
                    print(f'measured {index+1}/{len(inventory)} exact crops', flush=True)
        report['measurement_seconds'] = time.perf_counter()-started
        report['measurement'] = summarize(takes, rows, plans)
        by_key = {row['source_key']: row for row in report['measurement']['sources']}
        report['previously_flagged_sources'] = {key: by_key[key] for key in spec['previously_flagged_sources']}
        report['evidence'] = {evidence_path.name: dict(bytes=evidence_path.stat().st_size,
                                                     sha256=digest(evidence_path))}
        report['limits'] = spec['limits']
        report.update(state='completed', final=True,
            decision='Diagnostic only. All intended labels and all recorded scores remain unchanged.',
            stage='all exact crops measured; role and exposure totals reconciled')
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
    print(json.dumps(dict(state=result['state'], sources=result['measurement']['source_count'],
                          crops=result['measurement']['unique_crop_count'])))
