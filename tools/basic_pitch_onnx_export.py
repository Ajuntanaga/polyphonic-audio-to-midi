"""Exact-weight export into the existing experimental Neural Lab contract.

TensorFlow conversion and inference are GitHub-only. Array/manifest checks are
independent of those dependencies so malformed checkpoints fail before mutation.
This module makes no tracking-quality or live-host acceptance decision.
"""
import hashlib

import numpy as np

from tools.basic_pitch_streaming import ForwardDecoder
from tools.portable_basic_pitch_trainability import remote_only


INPUT = 'serving_default_input_2:0'
OUTPUTS = {'note': 'StatefulPartitionedCall:1', 'onset': 'StatefulPartitionedCall:2'}
INPUT_SHAPE = (1, 43844, 1)
OUTPUT_SHAPE = (1, 172, 88)


def variable_manifest(variables):
    return [dict(name=v.name, shape=list(v.shape), dtype=v.dtype.name) for v in variables]


def checked_weights(manifest, names, arrays):
    """Validate every model variable before the caller assigns any of them."""
    if not manifest or names != [v['name'] for v in manifest] or len(set(names)) != len(names):
        raise ValueError('Checkpoint variable order/names do not match the SavedModel')
    keys = {key for key in arrays if key.startswith('model_')}
    if keys != {f'model_{i}' for i in range(len(manifest))}:
        raise ValueError('Checkpoint model variable count differs')
    values = []
    for i, variable in enumerate(manifest):
        value = np.asarray(arrays[f'model_{i}'])
        if list(value.shape) != variable['shape'] or value.dtype != np.dtype(variable['dtype']):
            raise ValueError('Checkpoint shape/dtype differs: ' + variable['name'])
        if not np.isfinite(value).all():
            raise ValueError('Nonfinite checkpoint variable: ' + variable['name'])
        values.append(value.copy())
    return values


def weight_fingerprint(manifest, values):
    """Named, typed, ordered fingerprint; not just the NPZ container's digest."""
    import json
    digest = hashlib.sha256()
    if len(manifest) != len(values):
        raise ValueError('Variable manifest/array length mismatch')
    for variable, value in zip(manifest, values):
        metadata = json.dumps(variable, sort_keys=True, separators=(',', ':')).encode()
        digest.update(len(metadata).to_bytes(8, 'little'))
        digest.update(metadata)
        data = np.ascontiguousarray(value).tobytes()
        digest.update(len(data).to_bytes(8, 'little'))
        digest.update(data)
    return digest.hexdigest()


def checked_outputs(values):
    result = {}
    for key in OUTPUTS:
        value = np.asarray(values[key])
        if value.shape != OUTPUT_SHAPE or value.dtype != np.float32:
            raise ValueError('Wrong output shape/dtype: ' + key)
        if not np.isfinite(value).all() or (value < 0).any() or (value > 1).any():
            raise ValueError('Invalid probability output: ' + key)
        result[key] = value
    return result


def compare_outputs(reference, converted, tolerance):
    if not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError('Invalid numerical tolerance')
    left, right = checked_outputs(reference), checked_outputs(converted)
    metrics = {}
    for key in OUTPUTS:
        a, b = left[key].astype(np.float64), right[key].astype(np.float64)
        difference = np.abs(a-b)
        metrics[key] = dict(max_absolute=float(difference.max()),
            mean_absolute=float(difference.mean()),
            threshold_crossings={str(cut): int(np.count_nonzero((a >= cut) != (b >= cut)))
                                for cut in (0.3, 0.5)})
    # One continuous synthetic activation sequence per case. This detects event
    # differences even when the numerical tolerance alone would admit them.
    events = []
    for values in (left, right):
        decoder, sequence = ForwardDecoder(), []
        for i in range(172):
            sequence.extend(decoder.consume(values['note'][0, i].tolist(),
                                           values['onset'][0, i].tolist(), i))
        events.append(sequence)
    numerical = all(m['max_absolute'] <= tolerance for m in metrics.values())
    thresholds = all(not count for m in metrics.values() for count in m['threshold_crossings'].values())
    return dict(outputs=metrics, numerical_pass=numerical, thresholds_identical=thresholds,
        decoder_events_identical=events[0] == events[1],
        reference_event_count=len(events[0]), converted_event_count=len(events[1]),
        parity_pass=numerical and thresholds and events[0] == events[1])


def compare_streams(reference, converted, reference_events, converted_events, tolerance):
    """Compare saved readouts and causal decisions while excluding measured CPU time."""
    if not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError('Invalid numerical tolerance')
    frames = np.asarray(reference['frames'])
    if frames.ndim != 2 or frames.shape[1] != 4 or not len(frames):
        raise ValueError('Missing complete readout frame clock')
    if not np.array_equal(frames[:, 0], np.arange(len(frames))):
        raise ValueError('Readout frame clock is not consecutive')
    metrics, decoded = {}, []
    for key, cut in (('note', .3), ('onset', .5)):
        arrays = [np.asarray(table[key]) for table in (reference, converted)]
        for value in arrays:
            if (value.shape != (len(frames), 88) or value.dtype != np.float32
                    or not np.isfinite(value).all() or (value < 0).any() or (value > 1).any()):
                raise ValueError('Invalid saved activation table: ' + key)
        a, b = [value.astype(np.float64) for value in arrays]
        difference = np.abs(a-b)
        metrics[key] = dict(max_absolute=float(difference.max()),
            mean_absolute=float(difference.mean()), threshold=cut,
            threshold_crossings=int(np.count_nonzero((a >= cut) != (b >= cut))))
    for table, event_file in ((reference, reference_events), (converted, converted_events)):
        decoder, events = ForwardDecoder(), []
        for i, (notes, onsets) in enumerate(zip(table['note'], table['onset'])):
            events.extend(decoder.consume(notes.tolist(), onsets.tolist(), i))
        recorded = [{k: event[k] for k in ('kind', 'note', 'frame')}
                    for event in event_file['events']]
        if events != recorded:
            raise ValueError('Saved activations do not reproduce their own event sequence')
        decoded.append(events)
    causal = lambda data: [{k: event[k] for k in ('kind', 'note', 'frame', 'available_ns')}
                           for event in data['events']]
    clocks = np.array_equal(frames, np.asarray(converted['frames']))
    event_identity = causal(reference_events) == causal(converted_events)
    cleanup_identity = reference_events['cleanup']['notes'] == converted_events['cleanup']['notes']
    numerical = all(row['max_absolute'] <= tolerance for row in metrics.values())
    thresholds = all(row['threshold_crossings'] == 0 for row in metrics.values())
    return dict(readout_frames=len(frames), outputs=metrics, source_clocks_identical=clocks,
        numerical_pass=numerical, thresholds_identical=thresholds,
        decoder_events_identical=decoded[0] == decoded[1],
        source_available_events_identical=event_identity, cleanup_notes_identical=cleanup_identity,
        reference_events=len(decoded[0]), converted_events=len(decoded[1]),
        parity_pass=clocks and numerical and thresholds and event_identity and cleanup_identity,
        scope='All consumed readout frames and source-availability decisions; measured service time excluded')


def rename_contract(proto):
    """Rename a flat frozen graph, failing closed on unexpected control flow."""
    import onnx
    graph = proto.graph
    if len(graph.input) != 1 or len(graph.output) != 2:
        raise ValueError('Expected one input and ordered note/onset outputs')
    for node in graph.node:
        if any(a.type in (onnx.AttributeProto.GRAPH, onnx.AttributeProto.GRAPHS) for a in node.attribute):
            raise ValueError('Nested graph export requires an explicit scoped rename')
    old = [graph.input[0].name] + [value.name for value in graph.output]
    new = [INPUT] + list(OUTPUTS.values())
    if len(set(old)) != len(old):
        raise ValueError('Aliased graph input/output names')
    existing = {v for n in graph.node for v in (*n.input, *n.output)}
    existing.update(v.name for v in (*graph.input, *graph.output, *graph.initializer, *graph.value_info))
    mapping = dict(zip(old, new))
    if any(name in existing and name not in old for name in new):
        raise ValueError('Export contract name collides with an internal tensor')
    for node in graph.node:
        for field in (node.input, node.output):
            for i, name in enumerate(field):
                field[i] = mapping.get(name, name)
    for value in (*graph.input, *graph.output, *graph.initializer, *graph.value_info):
        value.name = mapping.get(value.name, value.name)
    for value, shape in [(graph.input[0], INPUT_SHAPE)] + [(v, OUTPUT_SHAPE) for v in graph.output]:
        tensor = value.type.tensor_type
        actual = tuple(d.dim_value if d.HasField('dim_value') else None for d in tensor.shape.dim)
        if tensor.elem_type != onnx.TensorProto.FLOAT or actual != shape:
            raise ValueError('Export does not implement the fixed Neural Lab tensor contract')
    onnx.checker.check_model(proto, full_check=True)
    return proto


def export_model(model, destination, opset=17):
    remote_only()
    import onnx
    import tensorflow as tf
    import tf2onnx
    if destination.exists():
        raise ValueError('Export destination already exists')
    before = [v.numpy().copy() for v in model.variables]
    signature = [tf.TensorSpec(INPUT_SHAPE, tf.float32, name='audio')]

    @tf.function(input_signature=signature, autograph=False)
    def serve(signal):
        values = model(signal)
        return tf.identity(values['note'], name='note'), tf.identity(values['onset'], name='onset')

    proto, storage = tf2onnx.convert.from_function(serve, input_signature=signature, opset=opset)
    if storage:
        raise ValueError('Unexpected external tensor storage')
    if not all(np.array_equal(v.numpy(), original) for v, original in zip(model.variables, before)):
        raise ValueError('Conversion mutated TensorFlow variables')
    rename_contract(proto)
    temporary = destination.with_suffix('.tmp')
    onnx.save_model(proto, str(temporary))
    temporary.replace(destination)
    return dict(bytes=destination.stat().st_size,
                sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                opset=opset, variables_preserved=True,
                inputs={INPUT: list(INPUT_SHAPE)},
                outputs={name: list(OUTPUT_SHAPE) for name in OUTPUTS.values()})
