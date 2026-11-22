"""Synthetic-only localization of an exact-weight TF/ONNX discrepancy.

Model work is restricted to GitHub Actions. No recording, fitting, output gate
change, or runtime-quality conclusion is part of this observation.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time

import numpy as np

from tools.basic_pitch_onnx_export import INPUT_SHAPE, compare_outputs
from tools.portable_basic_pitch_trainability import download_files, remote_only, save_report, synthetic_inputs


def array_difference(left, right):
    a, b = np.asarray(left), np.asarray(right)
    result = dict(reference_shape=list(a.shape), converted_shape=list(b.shape),
                  reference_dtype=str(a.dtype), converted_dtype=str(b.dtype))
    if a.shape != b.shape:
        return dict(result, comparable=False, reason='Different tensor layouts/shapes; no inferred permutation')
    if not a.size:
        return dict(result, comparable=False, reason='Empty intermediate tensor')
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        # A masked division can contain NaNs internally even when its selected
        # output is finite. Retain the observation; never call it a finite
        # parity pass or abort before recording the final-output comparisons.
        def counts(value):
            return dict(finite=int(np.isfinite(value).sum()),
                        nan=int(np.isnan(value).sum()),
                        positive_infinity=int(np.isposinf(value).sum()),
                        negative_infinity=int(np.isneginf(value).sum()))
        common = np.isfinite(a) & np.isfinite(b)
        same_kind = ((np.isnan(a) & np.isnan(b))
                     | (np.isposinf(a) & np.isposinf(b))
                     | (np.isneginf(a) & np.isneginf(b)))
        finite_delta = np.abs(a[common].astype(np.float64) - b[common].astype(np.float64))
        return dict(result, comparable=False, reason='Nonfinite intermediate tensor',
                    reference_nonfinite=counts(a), converted_nonfinite=counts(b),
                    nonfinite_kind_mismatches=int((~common & ~same_kind).sum()),
                    common_finite_elements=int(common.sum()),
                    common_finite_max_absolute=float(finite_delta.max()) if finite_delta.size else None)
    delta = np.abs(a.astype(np.float64) - b.astype(np.float64))
    index = int(delta.argmax())
    return dict(result, comparable=True, max_absolute=float(delta.flat[index]),
                mean_absolute=float(delta.mean()), unequal=int(np.count_nonzero(a != b)),
                reference_min=float(a.min()), reference_max=float(a.max()),
                converted_min=float(b.min()), converted_max=float(b.max()),
                max_index=[int(v) for v in np.unravel_index(index, a.shape)],
                reference_at_max=float(a.flat[index]), converted_at_max=float(b.flat[index]))


def choose_probes(tf_rows, onnx_names, maximum_count=256, maximum_elements=20000000):
    """Match exact tensor names and retain every eligible row within fixed bounds."""
    rows = [row for row in tf_rows if row['name'] in onnx_names
            and row['dtype'] == 'float32' and row['op'] not in ('Const', 'Placeholder')
            and row['shape'] is not None and all(d is not None and d > 0 for d in row['shape'])]
    elements = sum(int(np.prod(row['shape'])) for row in rows)
    if not rows or len(rows) > maximum_count or elements > maximum_elements:
        raise ValueError(f'Intermediate observation bounds exceeded/empty: {len(rows)} tensors, {elements} elements')
    return rows


def probe(spec, model_root, output, report, report_path):
    remote_only()
    import onnx
    import onnxruntime as ort
    import tensorflow as tf
    import tf2onnx
    from tensorflow.python.framework.convert_to_constants import convert_variables_to_constants_v2

    tf.config.set_visible_devices([], 'GPU')
    tf.config.threading.set_intra_op_parallelism_threads(1)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.experimental.enable_op_determinism()
    tf.random.set_seed(spec['seed'])
    model = tf.saved_model.load(str(model_root / spec['tensorflow_path']))
    original = [v.numpy().copy() for v in model.variables]
    signature = [tf.TensorSpec(INPUT_SHAPE, tf.float32, name='audio')]

    @tf.function(input_signature=signature, autograph=False)
    def serve(signal):
        values = model(signal)
        return tf.identity(values['note'], name='note'), tf.identity(values['onset'], name='onset')

    concrete = serve.get_concrete_function(*signature)
    frozen = convert_variables_to_constants_v2(concrete, lower_control_flow=False, aggressive_inlining=True)
    if len(frozen.inputs) != 1 or len(frozen.outputs) != 2:
        raise ValueError('Frozen boundary is not one input/two outputs')
    graph_def = frozen.graph.as_graph_def(add_shapes=True)
    proto, storage = tf2onnx.convert.from_graph_def(graph_def, name='basic_pitch_exact_weights',
        input_names=[frozen.inputs[0].name], output_names=[t.name for t in frozen.outputs], opset=17)
    if storage:
        raise ValueError('Unexpected external storage')
    bulk = output / 'bulk'
    bulk.mkdir()
    (bulk / 'frozen.pb').write_bytes(graph_def.SerializeToString())
    onnx.save_model(proto, str(bulk / 'unmodified.onnx'))
    tf_rows = []
    for op in frozen.graph.get_operations():
        for value in op.outputs:
            tf_rows.append(dict(name=value.name, op=op.type, dtype=value.dtype.name,
                shape=value.shape.as_list() if value.shape.rank is not None else None,
                inputs=[t.name for t in op.inputs]))
    onnx_rows = [dict(name=node.name, op=node.op_type, inputs=list(node.input), outputs=list(node.output))
                 for node in proto.graph.node]
    (bulk / 'graph-map.json').write_text(json.dumps(dict(tensorflow=tf_rows, onnx=onnx_rows), indent=2)+'\n')
    names = {name for node in proto.graph.node for name in node.output}
    selected = choose_probes(tf_rows, names, spec['maximum_probe_count'], spec['maximum_probe_elements'])
    report['probes'] = selected
    instrumented = copy.deepcopy(proto)
    already = {value.name for value in instrumented.graph.output}
    for row in selected:
        if row['name'] not in already:
            # No graph rewrite or conversion is performed. Runtime shapes are
            # checked before numeric comparison; layout changes are not guessed.
            instrumented.graph.output.append(onnx.helper.make_tensor_value_info(
                row['name'], onnx.TensorProto.FLOAT, None))
    onnx.save_model(instrumented, str(bulk / 'observed.onnx'))
    wrapped = tf.compat.v1.wrap_function(lambda: tf.import_graph_def(graph_def, name=''), [])
    fetched_names = list(dict.fromkeys([t.name for t in frozen.outputs] + [r['name'] for r in selected]))
    fetch = wrapped.prune(wrapped.graph.get_tensor_by_name(frozen.inputs[0].name),
                         [wrapped.graph.get_tensor_by_name(name) for name in fetched_names])

    def session(graph, optimized):
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = (ort.GraphOptimizationLevel.ORT_ENABLE_ALL if optimized
                                            else ort.GraphOptimizationLevel.ORT_DISABLE_ALL)
        return ort.InferenceSession(graph.SerializeToString(), options, providers=['CPUExecutionProvider'])

    sessions = {name: session(graph, optimized) for name, graph, optimized in (
        ('regular_optimized', proto, True), ('regular_unoptimized', proto, False),
        ('observed_optimized', instrumented, True), ('observed_unoptimized', instrumented, False))}
    outputs = [t.name for t in frozen.outputs]
    report['environment'] = dict(tensorflow=tf.__version__, tf2onnx=tf2onnx.__version__,
        onnx=onnx.__version__, onnxruntime=ort.__version__, numpy=np.__version__)
    report['cases'] = {}
    save_report(report_path, report)
    for case, signal in synthetic_inputs(spec, np).items():
        tensor = tf.convert_to_tensor(signal)
        live = {key: value.numpy() for key, value in model(tensor).items() if key in ('note', 'onset')}
        fixed = {key: value.numpy() for key, value in zip(('note', 'onset'), frozen(tensor))}
        tf_observed = dict(zip(fetched_names, [t.numpy() for t in fetch(tensor)]))
        row = dict(callable_vs_frozen=compare_outputs(live, fixed, spec['maximum_absolute']),
                   frozen_vs_observed=compare_outputs(fixed, dict(zip(('note', 'onset'),
                       [tf_observed[name] for name in outputs])), spec['maximum_absolute']), backends={})
        report['cases'][case] = row
        save_report(report_path, report)
        all_values = {}
        for name, runtime in sessions.items():
            all_values[name] = dict(zip([v.name for v in runtime.get_outputs()],
                                       runtime.run(None, {frozen.inputs[0].name: signal})))
            values = all_values[name]
            row['backends'][name] = dict(frozen_vs_onnx=compare_outputs(fixed,
                dict(zip(('note', 'onset'), [values[key] for key in outputs])), spec['maximum_absolute']))
            if name.startswith('observed'):
                base = all_values[name.replace('observed', 'regular')]
                row['backends'][name]['observation_perturbation'] = {
                    key: array_difference(base[value], values[value]) for key, value in zip(('note', 'onset'), outputs)}
                row['backends'][name]['intermediates'] = [dict(name=r['name'], op=r['op'],
                    **array_difference(tf_observed[r['name']], values[r['name']])) for r in selected]
            save_report(report_path, report)
        # Retain the bounded intermediate values remotely so a causal follow-up
        # can use the exact observation without repeating model execution.
        saved = {'tensorflow/' + name: value for name, value in tf_observed.items()}
        saved.update({'onnx_unoptimized/' + name: value
                      for name, value in all_values['observed_unoptimized'].items()})
        np.savez_compressed(bulk / (case + '-intermediates.npz'), **saved)
        save_report(report_path, report)
    report['variables_preserved'] = all(np.array_equal(v.numpy(), old) for v, old in zip(model.variables, original))
    if not report['variables_preserved']:
        raise ValueError('Observation changed model variables')
    report['state'] = 'localization_complete'
    report['scope'] = 'Synthetic numerical localization only; unchanged weights/gates; no corpus, fit or live readiness'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    remote_only()
    if os.environ.get('GITHUB_REPOSITORY') != 'Ajuntanaga/m3-offload':
        raise RuntimeError('Wrong worker repository')
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if source != os.environ.get('SOURCE_SHA'):
        raise RuntimeError('Source revision mismatch')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'report').mkdir()
    report_path = args.output / 'report/report.json'
    spec_bytes = args.spec.read_bytes()
    spec = json.loads(spec_bytes)
    report = dict(schema='m3_basic_pitch_onnx_numerics_v1', final=False,
        source_commit=source, run_id=os.environ.get('GITHUB_RUN_ID'),
        specification_sha256=hashlib.sha256(spec_bytes).hexdigest(),
        started_at=datetime.now(timezone.utc).isoformat(), state='downloading_public_model')
    save_report(report_path, report)
    started = time.perf_counter()
    try:
        report['public_model_files'] = download_files(spec, args.output / 'model')
        probe(spec, args.output / 'model', args.output, report, report_path)
    except Exception as error:
        report.update(state='error', error=repr(error))
        raise
    finally:
        report.update(final=True, elapsed_seconds=time.perf_counter()-started,
                      peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      finished_at=datetime.now(timezone.utc).isoformat())
        save_report(report_path, report)


if __name__ == '__main__':
    main()
