"""Fixed readout-only crop of one expensive convolution; no weight changes.

The model hash is pinned by the caller. Only final frames164/165 are valid and
exposed. Full input, CQT and normalization remain untouched. Learned-model
loading, transformation and inference are restricted to GitHub Actions.
"""
import hashlib

import numpy as np

from tools.basic_pitch_onnx_export import INPUT, OUTPUTS
from tools.basic_pitch_streaming import ForwardDecoder
from tools.portable_basic_pitch_comparison import remote_only


PREFIX = 'StatefulPartitionedCall/' * 4
TARGET = PREFIX + 'conv2d_1/StatefulPartitionedCall/BiasAdd'
READOUT_OUTPUTS = {'note': 'm3_readout_note', 'onset': 'm3_readout_onset'}
CROP_START = 154
READOUT_START = 164
READOUT_END = 166


def required_input_interval(start=164, end=166):
    """Inclusive/exclusive time dependency, onset head back to conv2d_1 input.

    Onset3 -> note7 -> features7 -> contour5 -> expensive3. Time stride is1
    throughout. Every right edge is clipped at172 to preserve SAME padding.
    """
    stages = []
    for name, radius in [('conv2d_5', 1), ('conv2d_3', 3), ('conv2d_2', 3),
                         ('contours-reduced', 2), ('conv2d_1', 1)]:
        start, end = max(0, start-radius), min(172, end+radius)
        stages.append(dict(node=name, required_start=start, required_end=end))
    return stages


def crop_model(source, destination):
    remote_only()
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    model = onnx.load(str(source), load_external_data=False)
    if any(value.data_location == TensorProto.EXTERNAL for value in model.graph.initializer):
        raise ValueError('External tensor data is not part of the pinned model')
    graph = model.graph
    if len(graph.node) != 242 or len(graph.input) != 1 or graph.input[0].name != INPUT:
        raise ValueError('Pinned graph/interface differs')
    if {value.name for value in graph.output} != set(OUTPUTS.values()):
        raise ValueError('Expected exactly the pinned note/onset outputs')
    if required_input_interval()[-1]['required_start'] != CROP_START:
        raise ValueError('Crop dependency differs')
    nodes = {node.name: node for node in graph.node}
    checks = {'conv2d_1': ([3,39], [1,19,1,19], [1,1]),
              'contours-reduced': ([5,5], [2,2,2,2], [1,1]),
              'conv2d_2': ([7,7], [3,2,3,2], [1,3]),
              'conv2d_3': ([7,3], [3,1,3,1], [1,1]),
              'conv2d_5': ([3,3], [1,1,1,1], [1,1])}
    for name, (kernel, pads, strides) in checks.items():
        node = nodes[PREFIX + name + '/StatefulPartitionedCall/BiasAdd']
        attrs = {a.name: helper.get_attribute_value(a) for a in node.attribute}
        if node.op_type != 'Conv' or attrs != dict(kernel_shape=kernel, pads=pads,
                strides=strides, dilations=[1,1], group=1):
            raise ValueError('Pinned temporal convolution differs: '+name)
    initial = {value.name: value.SerializeToString() for value in graph.initializer}
    if any(name.startswith('m3_crop_') for name in initial):
        raise ValueError('Crop already applied')
    target = nodes[TARGET]
    shapes = {v.name: list(v.dims) for v in graph.initializer}
    if shapes[target.input[1]] != [8,8,3,39] or shapes[target.input[2]] != [8]:
        raise ValueError('Expensive convolution weight shape differs')
    original_input, original_output = target.input[0], target.output[0]
    constants = {'starts': [CROP_START], 'ends': [172], 'axis': [2], 'steps': [1],
                 'pads': [0,0,CROP_START,0,0,0,0,0],
                 'readout_start': [READOUT_START], 'readout_end': [READOUT_END],
                 'readout_axis': [1]}
    for name, values in constants.items():
        graph.initializer.append(numpy_helper.from_array(np.array(values, dtype=np.int64),
                                                        name='m3_crop_'+name))
    before = helper.make_node('Slice', [original_input, 'm3_crop_starts', 'm3_crop_ends',
        'm3_crop_axis', 'm3_crop_steps'], ['m3_crop_input'], name='m3_crop_input_slice')
    target.input[0] = 'm3_crop_input'
    target.output[0] = 'm3_crop_output'
    after = helper.make_node('Pad', ['m3_crop_output', 'm3_crop_pads'], [original_output],
                             name='m3_crop_restore_shape', mode='constant')
    replaced = []
    for node in graph.node:
        if node.name == TARGET:
            replaced.extend([before, node, after])
        else:
            replaced.append(node)
    del graph.node[:]
    graph.node.extend(replaced)
    del graph.output[:]
    for key, original_name in OUTPUTS.items():
        graph.node.append(helper.make_node('Slice', [original_name, 'm3_crop_readout_start',
            'm3_crop_readout_end', 'm3_crop_readout_axis', 'm3_crop_steps'],
            [READOUT_OUTPUTS[key]], name='m3_crop_'+key+'_readout'))
        graph.output.append(helper.make_tensor_value_info(READOUT_OUTPUTS[key],
                                                          TensorProto.FLOAT, [1,2,88]))
    if any(initial[v.name] != v.SerializeToString() for v in graph.initializer if v.name in initial):
        raise ValueError('Original tensor changed')
    onnx.checker.check_model(model, full_check=True)
    onnx.save(model, str(destination))
    return dict(input_rows=[154,172], output_frames=[164,165], dependency=required_input_interval(),
        nodes_before=242, nodes_after=len(graph.node), original_initializers=len(initial),
        original_initializers_identical=True,
        original_initializer_fingerprint=hashlib.sha256(b''.join(initial[k] for k in sorted(initial))).hexdigest(),
        output_contract=dict(frame_origin=164, shape=[1,2,88]),
        limitation='Earlier outputs are invalid and are not exposed; not a full-window model.')


def compare_readout(reference, cropped, tolerance=1e-4):
    if tolerance != 1e-4:
        raise ValueError('Frozen readout tolerance differs')
    rows, values = {}, []
    for collection in (reference, cropped):
        checked = {}
        for key in OUTPUTS:
            value = np.asarray(collection[key])
            if value.shape != (2,88) or value.dtype != np.float32 or not np.isfinite(value).all():
                raise ValueError('Invalid two-frame readout: '+key)
            if (value < 0).any() or (value > 1).any():
                raise ValueError('Invalid probability: '+key)
            checked[key] = value
        values.append(checked)
    for key in OUTPUTS:
        a, b = values[0][key], values[1][key]
        difference = np.abs(a.astype(np.float64)-b.astype(np.float64))
        rows[key] = dict(max_absolute=float(difference.max()), mean_absolute=float(difference.mean()),
            bit_identical=np.array_equal(a,b),
            threshold_crossings={str(cut): int(np.count_nonzero((a >= cut) != (b >= cut)))
                                 for cut in (.3,.5)})
    sequences = []
    for item in values:
        decoder, events = ForwardDecoder(), []
        for i in range(2):
            events.extend(decoder.consume(item['note'][i], item['onset'][i], i))
        sequences.append(events)
    numerical = all(row['max_absolute'] <= tolerance for row in rows.values())
    thresholds = all(not count for row in rows.values() for count in row['threshold_crossings'].values())
    return dict(outputs=rows, numerical_pass=numerical, thresholds_identical=thresholds,
                decoder_events_identical=sequences[0] == sequences[1],
                parity_pass=numerical and thresholds and sequences[0] == sequences[1])
