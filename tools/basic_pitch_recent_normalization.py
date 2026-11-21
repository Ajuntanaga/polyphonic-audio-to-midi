"""One fixed normalization-support experiment; no recording or model I/O here."""
import copy
import time

from tools.basic_pitch_bass_view import View
from tools.basic_pitch_streaming import FifoClock

NORMALIZATION = dict(reference_time_range=[0, 172], candidate_time_range=[144, 172],
                     frequency_axis='all', readout_frames=[164, 165],
                     activation_identity_tolerance=1e-5)
MINIMUM = 'model_1/normalized_log_1/Min;model_1/normalized_log_1/Min'
RANGE = 'model_1/normalized_log_1/Max;model_1/normalized_log_1/Max'
LOG_POWER = 'model_1/normalized_log_1/mul;model_1/normalized_log_1/mul'
OFFSET = 'model_1/normalized_log_1/sub;model_1/normalized_log_1/sub'


def rewrite_normalization(original, recent):
    """Keep the graph/weights intact except the two reduction input slices."""
    import numpy as np
    import onnx
    from onnx import helper, numpy_helper
    model = copy.deepcopy(original)
    originals = {n.name: n.SerializeToString() for n in model.graph.node}
    weights = {v.name: v.SerializeToString() for v in model.graph.initializer}
    if len(originals) != len(model.graph.node):
        raise ValueError('Ambiguous graph node names')
    found, nodes = set(), []
    for node in model.graph.node:
        if node.name in (MINIMUM, RANGE):
            expected_type, expected_input = ('ReduceMin', LOG_POWER) if node.name == MINIMUM else ('ReduceMax', OFFSET)
            attrs = {a.name: helper.get_attribute_value(a) for a in node.attribute}
            if (node.op_type != expected_type or list(node.input) != [expected_input]
                    or list(node.output) != [node.name] or attrs != dict(axes=[1, 2], keepdims=0)):
                raise ValueError('Unexpected normalization reduction: ' + node.name)
            found.add(node.name)
            if recent:
                prefix = 'm3_recent_min' if node.name == MINIMUM else 'm3_recent_range'
                constants = []
                for suffix, value in (('start', 144), ('end', 172), ('axis', 1), ('step', 1)):
                    name = prefix + '_' + suffix
                    if name in weights:
                        raise ValueError('Normalization already modified')
                    model.graph.initializer.append(numpy_helper.from_array(np.array([value], dtype=np.int64), name))
                    constants.append(name)
                nodes.append(helper.make_node('Slice', [expected_input] + constants, [prefix], name=prefix))
                node.input[0] = prefix
        nodes.append(copy.deepcopy(node))
    if found != {MINIMUM, RANGE}:
        raise ValueError('Both normalization reductions are required')
    del model.graph.node[:]
    model.graph.node.extend(nodes)
    # Scalars already computed by the model; recording them adds no new reduction.
    for name in (MINIMUM, RANGE):
        if name in {out.name for out in model.graph.output}:
            raise ValueError('Normalization statistics already exposed')
        model.graph.output.append(helper.make_tensor_value_info(name, onnx.TensorProto.FLOAT, [None]))
    for node in model.graph.node:
        if node.name in originals and (not recent or node.name not in (MINIMUM, RANGE)):
            if node.SerializeToString() != originals[node.name]:
                raise ValueError('Unrelated graph node changed')
    after = {v.name: v.SerializeToString() for v in model.graph.initializer}
    if any(after.get(name) != value for name, value in weights.items()):
        raise ValueError('Original model initializer changed')
    onnx.checker.check_model(model, full_check=True)
    return model


def stream_pair(blocks, source_samples, reference_backend, candidate_backend,
                progress=None, clock_ns=time.perf_counter_ns):
    """Independent decoders on identical inputs, sharing one measured serial FIFO."""
    import numpy as np
    if type(source_samples) is not int or source_samples <= 0:
        raise ValueError('A positive complete source length is required')
    views = (View(reference_backend, 1), View(candidate_backend, 1))
    fifo, timing, source_end = FifoClock(), [], 0
    for block in blocks:
        started = clock_ns()
        block = np.asarray(block, dtype=np.float32)
        if block.ndim == 2:
            block = block.mean(axis=1, dtype=np.float32)
        if (block.ndim != 1 or not 0 < len(block) <= 640 or not np.isfinite(block).all()
                or source_end + len(block) > source_samples
                or (len(block) != 640 and source_end + len(block) != source_samples)):
            raise ValueError('Incomplete or invalid original source block')
        source_end += len(block)
        batches = [v.consume(block, source_end, source_end == source_samples, clock_ns) for v in views]
        service = clock_ns() - started
        arrival, finish, queued = fifo.submit(source_end, service)
        for view, batch in zip(views, batches):
            view.retain(batch, arrival, finish)
        timing.append((source_end, arrival, service, finish, queued,
            sum(b['resample_ns'] for b in batches), sum(b['model_ns'] for b in batches),
            sum(b['decode_ns'] for b in batches), int(batches[0]['activations'] is not None)))
        if progress and batches[0]['activations'] is not None and views[0].calls % 250 == 0:
            progress(views[0].calls, source_end)
    if source_end != source_samples or any(len(v.pending) for v in views):
        raise ValueError('Source ended before the promised complete recording')
    reference, candidate = (v.result() for v in views)
    if reference['frames'] != candidate['frames']:
        raise ValueError('Paired model frame mappings differ')
    return dict(reference=reference, candidate=candidate, timing=timing,
                source_samples=source_end, worker_finish_ns=fifo.finish_ns)


def assess(datasets):
    if set(datasets) != {'ordinary', 'extended-middle'}:
        raise ValueError('Both fixed recordings required for acceptance')
    comparisons = {name: row['arms']['candidate']['serviced']['comparison_to_reference']
                   for name, row in datasets.items()}
    gain = comparisons['ordinary']['pitch_coverage_gain_pp']
    return dict(ordinary_gain_pp=gain,
        incremental_screen_pass=gain > 0 and all(c['no_pitch_safety_regression'] for c in comparisons.values()),
        current_noninferiority_pass=all(row['arms']['candidate']['serviced']['comparison_to_current']
            ['no_pitch_safety_regression'] for row in datasets.values()),
        promotion_accepted=False, installed_output_changed=False)
