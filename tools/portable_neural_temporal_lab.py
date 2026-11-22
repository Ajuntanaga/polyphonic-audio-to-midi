"""Pinned prior/release corrected models through the actual experimental component.

GitHub CPU only. Collection and measurement are separate phases so the exact
release model can be packaged before running the component. No fit, decoder
change, policy search, installation or promotion is performed here.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

from tools.basic_pitch_streaming import CausalResampler, SETTINGS
from tools.pitch_detector_comparison import compare, digest
from tools.portable_artifact_subset import captured_api
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.portable_basic_pitch_native import NATIVE
from tools.portable_neural_lab import LAB, measure
from tools.portable_neural_ort_diagnosis import cpu_metadata


ARMS = ('prior', 'release')
DATASETS = ('ordinary', 'extended-middle')
CONTRACT = dict(readout_frames=[164,165], graph_optimizations='disabled',
    full_crop_bit_identity=True, cached_activation_absolute_tolerance=1e-5,
    cached_event_frame_source_eof_identity=True, primary_clock='component_delivery',
    model_count=2, native_pairs=4, component_passes=8, packaged_arm='release',
    quiet_gate=False, installed_output_changed=False, promotion_accepted=False)
MAX_SELECTED = 32 * 1024**2


def validate_spec(spec):
    if (spec['schema'] != 'm3_neural_temporal_lab_spec_v1'
            or spec['worker_repository'] != 'Ajuntanaga/m3-offload'
            or spec['streaming_settings'] != SETTINGS or spec['lab_settings'] != LAB
            or spec['native_settings'] != NATIVE or spec['contract'] != CONTRACT
            or set(spec['datasets']) != set(DATASETS)):
        raise ValueError('Frozen temporal integration configuration differs')
    producer = spec['producer']
    for key in ('source_commit', 'worker_commit'):
        if not re.fullmatch('[0-9a-f]{40}', producer[key]):
            raise ValueError('Missing producer revision')
    for key in ('report_artifact', 'evidence_artifact'):
        pin = producer[key]
        if (pin['run_id'] != producer['run_id'] or pin['worker_commit'] != producer['worker_commit']
                or not isinstance(pin['id'], int) or not 0 < pin['bytes'] <= 2*1024**3
                or not re.fullmatch('[0-9a-f]{64}', pin['sha256'])):
            raise ValueError('Invalid producer artifact pin')


def validate_report(report, spec):
    producer = spec['producer']
    if (report['schema'] != 'm3_basic_pitch_release_adaptation_v1'
            or report['final'] is not True or report['state'] != 'complete'
            or int(report['run_id']) != producer['run_id']
            or report['source_commit'] != producer['source_commit']
            or report['worker_commit'] != producer['worker_commit']
            or report['specification_sha256'] != producer['specification_sha256']
            or report['specification']['streaming'] != SETTINGS
            or report['specification']['datasets'] != spec['datasets']
            or set(report['datasets']) != set(DATASETS)):
        raise ValueError('Producer report provenance or source configuration differs')
    for arm in ARMS:
        export = report['exports'][arm]
        if (export['synthetic_parity_pass'] is not True
                or export['crop']['original_initializers_identical'] is not True
                or export['crop']['output_contract'] != dict(frame_origin=164,shape=[1,2,88])):
            raise ValueError('Corrected export/readout identity was not established')
        for name in DATASETS:
            if report['datasets'][name]['backend_parity'][arm]['parity_pass'] is not True:
                raise ValueError('Producer corpus backend parity failed')


def evidence_members(report):
    """Select only models and cropped reference tapes; no audio or weights."""
    result = {}
    for arm in ARMS:
        export = report['exports'][arm]
        result[arm+'.onnx'] = dict(sha256=export['full_model']['sha256'],
                                  bytes=export['full_model']['bytes'])
        # The producer records a content hash but not a size for this graph.
        # The complete archive is also pinned; bound its expansion explicitly.
        result[arm+'-readout.onnx'] = dict(sha256=export['cropped_sha256'], maximum_bytes=2*1024**2)
        for name in DATASETS:
            row = report['datasets'][name]['arms'][arm+'_cropped']
            for suffix in ('-stream.npz','-events.json'):
                key = name+suffix
                result[arm+'_cropped/'+key] = row['bulk'][key]
    return result


def extract_members(archive, members, destination):
    """Verify all named members before writing any; no archive path traversal."""
    selected = {}
    with zipfile.ZipFile(archive) as bundle:
        for name, pin in members.items():
            relative = PurePosixPath(name)
            if (relative.is_absolute() or '..' in relative.parts or '\\' in name
                    or str(relative) != name or not re.fullmatch('[0-9a-f]{64}',pin['sha256'])):
                raise ValueError('Invalid selected path or hash')
            matches = [entry for entry in bundle.infolist() if entry.filename == name]
            if len(matches) != 1:
                raise ValueError('Missing or duplicate selected member: '+name)
            entry = matches[0]
            maximum = pin.get('bytes',pin.get('maximum_bytes',0))
            if (entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1
                    or not 0 < entry.file_size <= maximum
                    or ('bytes' in pin and entry.file_size != pin['bytes'])):
                raise ValueError('Selected member type or size differs: '+name)
            if sum(len(data) for data in selected.values())+entry.file_size > MAX_SELECTED:
                raise ValueError('Selected evidence budget exceeded')
            data = bundle.read(entry)
            if hashlib.sha256(data).hexdigest() != pin['sha256']:
                raise ValueError('Selected member hash differs: '+name)
            selected[name] = data
    destination.mkdir(parents=True,exist_ok=False)
    for name, data in selected.items():
        path = destination/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    return {name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            for name,data in selected.items()}


def collect(pin, repository, folder, members):
    folder.mkdir()
    metadata = folder/'artifact.json'
    captured_api(f"repos/{repository}/actions/artifacts/{pin['id']}",metadata,45)
    actual = json.loads(metadata.read_bytes())
    if (any(actual[key] != pin[key] for key in ('id','name'))
            or actual['workflow_run']['id'] != pin['run_id']
            or actual['workflow_run']['head_sha'] != pin['worker_commit']
            or actual.get('digest') != 'sha256:'+pin['sha256']
            or actual['size_in_bytes'] != pin['bytes'] or actual['expired']):
        raise ValueError('Artifact provenance differs')
    archive = folder/'artifact.zip'
    captured_api(f"repos/{repository}/actions/artifacts/{pin['id']}/zip",archive,480)
    if archive.stat().st_size != pin['bytes']:
        raise ValueError('Downloaded artifact size differs')
    check_hash(archive,pin['sha256'])
    return extract_members(archive,members,folder/'selected')


def dispatch_identity(spec):
    source = captured_text(['git','rev-parse','HEAD'])
    if source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
        raise ValueError('Dispatch source/worker differs')
    return source


def prepare(spec_path, output):
    remote_only()
    spec = json.loads(spec_path.read_text());validate_spec(spec)
    source = dispatch_identity(spec)
    output.mkdir(parents=True,exist_ok=False)
    producer = spec['producer']
    report_pin = producer['report_member']
    collected_report = collect(producer['report_artifact'],spec['worker_repository'],
        output/'producer-report',{report_pin['path']:{k:report_pin[k] for k in ('bytes','sha256')}})
    report = json.loads((output/'producer-report/selected'/report_pin['path']).read_text())
    validate_report(report,spec)
    files = collect(producer['evidence_artifact'],spec['worker_repository'],output/'evidence',evidence_members(report))
    receipt = dict(schema='m3_neural_temporal_prepared_v1',source_commit=source,
        specification_sha256=digest(spec_path),producer=producer,report_files=collected_report,
        files=files,release_model_sha256=report['exports']['release']['cropped_sha256'],
        collected_at=datetime.now(timezone.utc).isoformat(),verified=True)
    save_json(output/'receipt.json',receipt)
    return receipt


def assess(datasets):
    integration = all(datasets[name][arm]['integration_pass'] for name in DATASETS for arm in ARMS)
    quality, paired = {}, {}
    for fmt in ('32','64'):
        complete = all(datasets[name][arm]['formats'][fmt].get('state') == 'measured'
                       for name in DATASETS for arm in ARMS)
        quality[fmt] = False;paired[fmt] = {}
        if not complete:
            continue
        for name in DATASETS:
            before, after = [datasets[name][arm]['formats'][fmt]['views']['component_delivery'] for arm in ARMS]
            paired[fmt][name] = compare(before['measurement'],after['measurement'])
        release = {name:datasets[name]['release']['formats'][fmt]['views']['component_delivery'] for name in DATASETS}
        quality[fmt] = (release['ordinary']['comparison_to_current']['pitch_coverage_gain_pp'] >= 5
            and all(row['comparison_to_current']['no_pitch_safety_regression'] for row in release.values())
            and all(row['no_pitch_safety_regression'] for row in paired[fmt].values()))
    return dict(component_integration_pass=integration,release_vs_prior_primary=paired,
        strict_pitch_replacement_by_format=quality,strict_pitch_replacement_pass=all(quality.values()),
        promotion_accepted=False,installed_output_changed=False)


def run(spec_path, prepared, inputs, harness, checker, bundle, output):
    remote_only()
    spec = json.loads(spec_path.read_text());validate_spec(spec)
    source = dispatch_identity(spec)
    receipt = json.loads((prepared/'receipt.json').read_text())
    if (receipt['source_commit'] != source or receipt['specification_sha256'] != digest(spec_path)
            or receipt['producer'] != spec['producer'] or receipt['verified'] is not True):
        raise ValueError('Prepared provenance differs')
    report_pin = spec['producer']['report_member']
    fit_path = prepared/'producer-report/selected'/report_pin['path']
    check_hash(fit_path,report_pin['sha256'])
    fit = json.loads(fit_path.read_text());validate_report(fit,spec)
    models = prepared/'evidence/selected'
    for name,pin in evidence_members(fit).items():
        check_hash(models/name,pin['sha256'])
    if os.environ.get('INPUT_SHA256') != spec['input_bundle_sha256']:
        raise ValueError('Input archive pin differs')
    check_hash(inputs/'recovery-inputs.json',spec['input_manifest_sha256'])
    root = Path(__file__).resolve().parents[1]
    baseline_pin = spec['baseline'];check_hash(root/baseline_pin['path'],baseline_pin['sha256'])
    baseline = json.loads((root/baseline_pin['path']).read_text())
    resources = bundle/'Contents/Resources'
    check_hash(resources/'nmp.onnx',fit['exports']['release']['cropped_sha256'])
    if (resources/'coefficients.f64').read_bytes() != CausalResampler().h.astype('<f8').tobytes():
        raise ValueError('Packaged filter differs')
    for name,config in spec['datasets'].items():
        for ext,key in (('wav','wav_sha256'),('tsv','labels_sha256')):
            check_hash(inputs/'corpus'/(name+'.'+ext),config[key])
    output.mkdir(parents=True,exist_ok=False)
    folders = {k:output/k for k in ('report','logs','scratch','bulk')}
    for path in folders.values():path.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_neural_temporal_lab_v1',state='running',final=False,datasets={},
        source_commit=source,worker_commit=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],
        specification=spec,specification_sha256=digest(spec_path),collection=receipt,
        producer_screen=fit['screen'],installed_output_changed=False,promotion_accepted=False,
        started_at=datetime.now(timezone.utc).isoformat(),cpu_before=cpu_metadata(),
        harness_sha256=digest(harness),checker_sha256=digest(checker),ort_sdk_sha256=os.environ['ORT_SDK_SHA256'],
        package_model_sha256=digest(resources/'nmp.onnx'),
        interpretation='Actual accepting component and separate relocated package smoke. Primary clock is accepted callback wall time. Worker-ready and source availability are diagnostics. Corrected full/crop native readouts must be bit-identical; Python cache tolerance remains 1e-5 with exact events/frame/source/EOF. Native allocation/deadline gates are separate from pitch quality. No external DAW, device, string, MPE, bend or unison-multiplicity acceptance.')
    save_json(report_path,report)
    try:
        for name in DATASETS:
            report['datasets'][name] = {}
            for arm in ARMS:
                report['stage'] = name+' '+arm+' paired native identity and component delivery'
                save_json(report_path,report)
                dest = {k:folders[k]/arm for k in ('logs','scratch','bulk')}
                for path in dest.values():path.mkdir(exist_ok=True)
                refs = dict(baseline=baseline,stream=dict(datasets={name:fit['datasets'][name]['arms'][arm+'_cropped']}))
                report['datasets'][name][arm] = measure(name,spec['datasets'][name],refs,inputs,
                    models/(arm+'_cropped'),models/(arm+'-readout.onnx'),harness,
                    dest['scratch'],dest['logs'],dest['bulk'],
                    crop=dict(checker=checker,original=models/(arm+'.onnx'),corrected=True))
                save_json(report_path,report)
        report.update(state='complete',screen=assess(report['datasets']))
    except Exception as error:
        report.update(state='failed',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report.update(final=True,finished_at=datetime.now(timezone.utc).isoformat(),cpu_after=cpu_metadata())
        save_json(report_path,report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='phase',required=True)
    collect_parser = sub.add_parser('prepare')
    for name in ('spec-path','output'):collect_parser.add_argument('--'+name,type=Path,required=True)
    run_parser = sub.add_parser('measure')
    for name in ('spec-path','prepared','inputs','harness','checker','bundle','output'):
        run_parser.add_argument('--'+name,type=Path,required=True)
    args = vars(parser.parse_args(argv));phase=args.pop('phase')
    result = prepare(**args) if phase == 'prepare' else run(**args)
    print(json.dumps(result.get('screen',dict(prepared=result.get('verified'))),allow_nan=False))
    return 0 if phase == 'prepare' or result['screen']['component_integration_pass'] else 1


if __name__ == '__main__':raise SystemExit(main())
