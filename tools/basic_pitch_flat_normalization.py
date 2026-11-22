"""Exact constant-power normalization correction for an uninstalled model.

The original calculation is retained for every nonconstant spectral window.
All model execution and graph conversion belong on the authorized CPU worker.
"""
import copy

from tools.basic_pitch_onnx_export import INPUT_SHAPE, OUTPUT_SHAPE
from tools.portable_basic_pitch_comparison import remote_only


POWER_SUFFIX = '/normalized_log_1/PartitionedCall/Square'
NORMALIZED_SUFFIX = '/normalized_log_1/PartitionedCall/Reshape_2'
SPECTRAL_SHAPE = (1, 172, 309)
CORRECTION = dict(predicate='Exact minimum(power)==maximum(power) across axes1,2',
    constant_output=0, nonconstant='Original calculation unchanged',
    epsilon_added=False, weights_changed=False, decoder_changed=False)


def locate_boundary(graph_def):
    def one(suffix, kind):
        rows = [node for node in graph_def.node if node.name.endswith(suffix)]
        if len(rows) != 1 or rows[0].op != kind:
            raise ValueError('Unexpected normalization boundary: '+suffix)
        return rows[0].name
    return one(POWER_SUFFIX, 'Square'), one(NORMALIZED_SUFFIX, 'Reshape')


def guard_graph(graph_def, power_name, normalized_name):
    """Append a primitive constant-window guard and rewire only its consumers."""
    remote_only()
    import tensorflow as tf

    result = copy.deepcopy(graph_def)
    names = {node.name for node in result.node}
    if power_name not in names or normalized_name not in names:
        raise ValueError('Guard boundary is absent')
    graph = tf.Graph()
    with graph.as_default(), tf.name_scope('flat_guard'):
        power = tf.compat.v1.placeholder(tf.float32, SPECTRAL_SHAPE, name='power')
        normalized = tf.compat.v1.placeholder(tf.float32, SPECTRAL_SHAPE, name='normalized')
        flat = tf.equal(tf.reduce_min(power, [1, 2], keepdims=True),
                        tf.reduce_max(power, [1, 2], keepdims=True), name='is_constant')
        selected = tf.where(flat, tf.zeros_like(normalized), normalized, name='output')
    addition = graph.as_graph_def(add_shapes=True)
    added = [node for node in addition.node if node.op != 'Placeholder']
    if names.intersection(node.name for node in added):
        raise ValueError('Guard node collision')
    replacements = {'flat_guard/power': power_name, 'flat_guard/normalized': normalized_name}
    for node in added:
        for i, value in enumerate(node.input):
            if value in replacements:
                node.input[i] = replacements[value]
            elif value.endswith(':0') and value[:-2] in replacements:
                node.input[i] = replacements[value[:-2]]+':0'
    consumers = 0
    for node in result.node:
        for i, value in enumerate(node.input):
            if value in (normalized_name, normalized_name+':0'):
                node.input[i] = selected.name
                consumers += 1
    if not consumers:
        raise ValueError('Normalization output has no consumers')
    result.node.extend(added)
    return result, dict(power_tensor=power_name+':0', original_normalized=normalized_name+':0',
        corrected_normalized=selected.name, rewired_edges=consumers,
        added_nodes=len(added), predicate='Exact reduce_min(power)==reduce_max(power), axes1,2',
        constant_output=0, nonconstant_calculation='Unchanged original normalization')


def corrected_model(model):
    remote_only()
    import numpy as np
    import tensorflow as tf
    from tensorflow.python.framework.convert_to_constants import convert_variables_to_constants_v2

    before = [value.numpy().copy() for value in model.variables]

    @tf.function(input_signature=[tf.TensorSpec(INPUT_SHAPE, tf.float32, name='audio')], autograph=False)
    def serve(signal):
        values = model(signal)
        return tf.identity(values['note'], name='note'), tf.identity(values['onset'], name='onset')

    frozen = convert_variables_to_constants_v2(serve.get_concrete_function(),
        lower_control_flow=False, aggressive_inlining=True)
    if (len(frozen.inputs) != 1 or len(frozen.outputs) != 2
            or tuple(frozen.inputs[0].shape) != INPUT_SHAPE
            or any(tuple(value.shape) != OUTPUT_SHAPE for value in frozen.outputs)):
        raise ValueError('Unexpected frozen model signature')
    graph_def = frozen.graph.as_graph_def(add_shapes=True)
    power, normalized = locate_boundary(graph_def)
    for name in (power, normalized):
        if tuple(frozen.graph.get_tensor_by_name(name+':0').shape) != SPECTRAL_SHAPE:
            raise ValueError('Unexpected spectral tensor shape')
    rewritten, metadata = guard_graph(graph_def, power, normalized)
    wrapped = tf.compat.v1.wrap_function(lambda: tf.import_graph_def(rewritten, name=''), [])
    call = wrapped.prune(wrapped.graph.get_tensor_by_name(frozen.inputs[0].name),
        [wrapped.graph.get_tensor_by_name(value.name) for value in frozen.outputs])
    if not all(np.array_equal(value.numpy(), old) for value, old in zip(model.variables, before)):
        raise ValueError('Correction changed model variables')

    class FrozenCorrected:
        variables = model.variables

        def __call__(self, signal):
            return dict(zip(('note', 'onset'), call(signal)))

    return FrozenCorrected(), metadata


def checked_pair(values):
    """Validate the actual two-output corrected interface, without a contour head."""
    import numpy as np
    if set(values) != {'note', 'onset'}:
        raise ValueError('Unexpected corrected model outputs')
    for name, value in values.items():
        if (value.shape != OUTPUT_SHAPE or not np.isfinite(value).all()
                or np.any((value < 0) | (value > 1))):
            raise ValueError('Invalid corrected model probabilities: '+name)
    return values['note'][0], values['onset'][0]


class CorrectedBackend:
    """Causal streaming adapter for the corrected, frozen two-output model."""
    def __init__(self, model, tf):
        remote_only()
        import numpy as np
        import soundfile as sf
        self.model, self.tf, self.np, self.sf = model, tf, np, sf
        self.predict(np.zeros(INPUT_SHAPE[1], np.float32))

    def predict(self, signal):
        tensor = self.tf.convert_to_tensor(signal.reshape(INPUT_SHAPE))
        return checked_pair({key: value.numpy() for key, value in self.model(tensor).items()})
