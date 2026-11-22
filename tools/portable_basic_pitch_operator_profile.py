"""Bounded, synthetic-only operator profile of the pinned disabled-ORT graph.

Profiling is observational. It neither chooses a policy nor establishes a
corpus deadline. All model execution is restricted to GitHub Actions.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from tools.pitch_detector_comparison import digest
from tools.portable_basic_pitch_comparison import remote_only, save_json
from tools.portable_basic_pitch_onnx_export import collect_reference
from tools.portable_basic_pitch_trainability import synthetic_inputs


def summarize_profile(events, expected_calls):
    calls = [e for e in events if e.get('name') == 'model_run' and e.get('ph') == 'X']
    calls.sort(key=lambda e: e['ts'])
    if len(calls) != expected_calls + 1:
        raise ValueError(f'Expected one warmup and {expected_calls} calls, got {len(calls)}')
    nodes = defaultdict(list)
    types = defaultdict(float)
    for call in calls[1:]:
        start, end = call['ts'], call['ts'] + call['dur']
        matched = [e for e in events if e.get('cat') == 'Node'
                   and e.get('name', '').endswith('_kernel_time')
                   and e.get('ph') == 'X' and start <= e['ts'] < end
                   and e['ts'] + e['dur'] <= end + 1]
        if not matched:
            raise ValueError('No kernel events in a measured model call')
        for event in matched:
            args = event.get('args', {})
            key = (event['name'], args.get('op_name'), args.get('provider'))
            nodes[key].append(float(event['dur']))
            types[args.get('op_name', 'unknown')] += float(event['dur'])
    total = sum(sum(v) for v in nodes.values())
    rows = [dict(name=k[0], op_type=k[1], provider=k[2], calls=len(v),
                 total_us=sum(v), mean_us=sum(v)/len(v), maximum_us=max(v),
                 share_of_kernel_duration=sum(v)/total if total else 0)
            for k, v in nodes.items()]
    rows.sort(key=lambda row: (-row['total_us'], row['name']))
    return dict(measured_calls=expected_calls, warmup_calls_excluded=1,
                profiled_model_run_us=[float(c['dur']) for c in calls[1:]],
                total_kernel_us=total, nodes=rows,
                op_types=[dict(op_type=k, total_us=v, share_of_kernel_duration=v/total if total else 0)
                          for k, v in sorted(types.items(), key=lambda p: -p[1])])


def graph_metadata(path):
    import onnx
    graph = onnx.shape_inference.infer_shapes(onnx.load(str(path))).graph
    shapes = {}
    for value in list(graph.input) + list(graph.value_info) + list(graph.output):
        tensor = value.type.tensor_type
        shapes[value.name] = dict(dtype=tensor.elem_type, shape=[
            dim.dim_value if dim.HasField('dim_value') else dim.dim_param or None
            for dim in tensor.shape.dim])
    initializers = {}
    for value in graph.initializer:
        item = dict(dtype=value.data_type, shape=list(value.dims))
        # Only small integer graph constants, never learned float weights.
        if value.data_type in (onnx.TensorProto.INT32, onnx.TensorProto.INT64):
            array = onnx.numpy_helper.to_array(value)
            if array.size <= 16:
                item['integers'] = array.tolist()
        initializers[value.name] = item
    nodes = []
    for node in graph.node:
        attributes = {}
        for attr in node.attribute:
            value = onnx.helper.get_attribute_value(attr)
            if isinstance(value, onnx.TensorProto):
                attributes[attr.name] = dict(dtype=value.data_type, shape=list(value.dims))
            elif isinstance(value, onnx.GraphProto):
                attributes[attr.name] = dict(graph=value.name, nodes=len(value.node))
            elif isinstance(value, bytes):
                attributes[attr.name] = value.decode('utf-8', errors='replace')
            else:
                attributes[attr.name] = value
        nodes.append(dict(name=node.name, op_type=node.op_type, domain=node.domain,
                          inputs=list(node.input), outputs=list(node.output), attributes=attributes))
    return dict(nodes=nodes, tensors=shapes, initializers=initializers)


def session(path, profile_prefix=None):
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    if profile_prefix is not None:
        options.enable_profiling = True
        options.profile_file_prefix = str(profile_prefix)
    result = ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])
    if result.get_providers() != ['CPUExecutionProvider']:
        raise ValueError('Expected CPU-only execution')
    return result


def run(spec_path, output):
    remote_only()
    import numpy as np
    import onnxruntime as ort
    spec = json.loads(spec_path.read_text())
    source = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True,
                            text=True, check=True).stdout.strip()
    if source != os.environ['SOURCE_SHA'] or os.environ['GITHUB_REPOSITORY'] != spec['worker_repository']:
        raise ValueError('Dispatch/source mismatch')
    if spec['repeats'] != 16 or spec['onnxruntime_version'] != ort.__version__:
        raise ValueError('Frozen profile protocol mismatch')
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache', 'reference', 'bulk')}
    for path in folders.values():
        path.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_basic_pitch_operator_profile_v1', state='running', final=False,
        source_commit=source, worker_commit=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
        started_at=datetime.now(timezone.utc).isoformat(), specification=spec,
        specification_sha256=digest(spec_path), models={},
        environment=dict(python=sys.version, platform=platform.platform(), onnxruntime=ort.__version__,
                         numpy=np.__version__, intra_threads=2, inter_threads=1, graph_optimization='disabled'),
        installed_output_changed=False, promotion_accepted=False,
        interpretation='Synthetic operator cost localization only. Profiling adds overhead; '
                       'no corpus p99/deadline, note-quality or live-readiness conclusion.')
    save_json(report_path, report)
    try:
        models = collect_reference(spec, folders)
        signals = synthetic_inputs(spec['synthetic'], np)
        names = ['StatefulPartitionedCall:1', 'StatefulPartitionedCall:2']
        zero = {'serving_default_input_2:0': np.zeros((1, 43844, 1), dtype=np.float32)}
        for arm in ('unmodified', 'adapted'):
            graph = graph_metadata(models[arm+'.onnx'])
            save_json(folders['report']/(arm+'-graph.json'), graph)
            row = dict(model=spec['reference_members'][arm+'.onnx'], cases={}, graph_nodes=len(graph['nodes']))
            report['models'][arm] = row
            for name, signal in signals.items():
                feed = {'serving_default_input_2:0': signal.reshape(1, 43844, 1).astype(np.float32)}
                plain = session(models[arm+'.onnx'])
                plain.run(names, zero)
                baseline = plain.run(names, feed)
                del plain
                profiled = session(models[arm+'.onnx'], folders['bulk']/(arm+'-'+name))
                profiled.run(names, zero)
                elapsed = []
                identical = True
                for _ in range(spec['repeats']):
                    start = time.perf_counter_ns()
                    values = profiled.run(names, feed)
                    elapsed.append(time.perf_counter_ns()-start)
                    identical = identical and all(np.array_equal(a, b) for a, b in zip(baseline, values))
                profile_path = Path(profiled.end_profiling())
                del profiled
                raw = json.loads(profile_path.read_text())
                summary = summarize_profile(raw, spec['repeats'])
                row['cases'][name] = dict(output_bit_identical_to_unprofiled=identical,
                    wall_service_with_profiling_ns=elapsed, **summary,
                    raw_profile=dict(file=profile_path.name, bytes=profile_path.stat().st_size,
                                     sha256=digest(profile_path)))
                save_json(report_path, report)
                if not identical:
                    raise ValueError('Profiling changed output; cost attribution invalid')
        report['state'] = 'complete'
        report['observation_integrity_pass'] = True
        return report
    except Exception as error:
        report['state'] = 'failed'
        report['error'] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        report['final'] = True
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        save_json(report_path, report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.spec, args.output)
