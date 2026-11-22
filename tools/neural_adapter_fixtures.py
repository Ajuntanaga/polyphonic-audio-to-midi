"""Tiny synthetic ONNX contract fixtures for the GitHub-only native adapter test.

These are arithmetic test graphs, not trained models or recorded audio.
"""
import argparse
from pathlib import Path

import numpy as np

from tools.portable_basic_pitch_comparison import remote_only


def create(destination):
    remote_only()
    import onnx
    from onnx import TensorProto, helper, numpy_helper
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    normal_input = 'serving_default_input_2:0'
    normal_outputs = ['StatefulPartitionedCall:1', 'StatefulPartitionedCall:2']
    temporal_outputs = ['m3_readout_note', 'm3_readout_onset']
    variants = [
        ('full', 172, normal_input, normal_outputs, 43844, False),
        ('legacy-crop', 2, normal_input, normal_outputs, 43844, True),
        ('temporal', 2, normal_input, temporal_outputs, 43844, False),
        ('wrong-input', 2, 'unexpected_input', temporal_outputs, 43844, False),
        ('wrong-input-shape', 2, normal_input, temporal_outputs, 43843, False),
        ('wrong-output-shape', 3, normal_input, temporal_outputs, 43844, False),
        ('missing-legacy-metadata', 2, normal_input, normal_outputs, 43844, False),
    ]
    for name, frames, input_name, outputs, input_length, metadata in variants:
        origin = 0 if frames == 172 else 164
        row = np.arange(origin, origin+frames, dtype=np.float32)[:, None]
        pitch = np.arange(88, dtype=np.float32)[None, :]
        # NumPy 1.x promotes a float32 array divided by the integer 65536.
        # Keep every operand float32 to match the ONNX FLOAT interface.
        note = (row/np.float32(256) + pitch/np.float32(65536))[None]
        onset = (np.float32(.5) + row/np.float32(512) + pitch/np.float32(65536))[None]
        assert note.dtype == onset.dtype == np.dtype('float32')
        tensors = [numpy_helper.from_array(note, 'note_values'),
                   numpy_helper.from_array(onset, 'onset_values'),
                   numpy_helper.from_array(np.array(1/64, np.float32), 'scale')]
        nodes = [helper.make_node('ReduceMean', [input_name], ['input_mean'],
                                  axes=[0,1,2], keepdims=0),
                 helper.make_node('Mul', ['input_mean','scale'], ['input_shift'])]
        for tensor, output in zip(('note_values','onset_values'), outputs):
            nodes.append(helper.make_node('Add', [tensor,'input_shift'], [output]))
        graph = helper.make_graph(nodes, name,
            [helper.make_tensor_value_info(input_name, TensorProto.FLOAT, [1,input_length,1])],
            [helper.make_tensor_value_info(n, TensorProto.FLOAT, [1,frames,88]) for n in outputs],
            initializer=tensors)
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 13)], ir_version=9)
        if metadata:
            for key, value in {
                'm3.crop.schema': 'm3_basic_pitch_readout164_165_tail144_v1',
                'm3.crop.parent_sha256': '2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec',
            }.items():
                entry = model.metadata_props.add()
                entry.key, entry.value = key, value
        onnx.checker.check_model(model, full_check=True)
        onnx.save(model, destination/(name+'.onnx'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination')
    create(parser.parse_args().destination)
