"""Fixed temporal CNN crop for the pinned Basic Pitch model; no inference here."""
import argparse
import hashlib
import json
from pathlib import Path

PARENT_SHA256 = '2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec'
SCHEMA = 'm3_basic_pitch_readout164_165_tail144_v1'
CROP_START, CROP_END = 144, 172
READOUT = (164, 165)
SHAPES = {
    'StatefulPartitionedCall:0_shape__746': ([-1,172,264], [-1,28,264]),
    'new_shape__614': ([-1,1,172,264], [-1,1,28,264]),
    'StatefulPartitionedCall:2_shape__747': ([-1,172,88], [-1,28,88]),
}


def export(source, destination, report_path):
    import numpy as np
    import onnx
    from onnx import helper, numpy_helper
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != PARENT_SHA256:
        raise ValueError('Crop only supports the pinned original model')
    model = onnx.load_model_from_string(data)
    nodes = list(model.graph.node)
    if len(nodes) != 248 or nodes[209].op_type != 'Reshape' or nodes[210].op_type != 'Unsqueeze':
        raise ValueError('Unexpected normalized-CQT boundary')
    upstream = [node.SerializeToString() for node in nodes[:210]]
    original_initializers = {value.name: value.SerializeToString() for value in model.graph.initializer}
    found = set()
    for value in model.graph.initializer:
        if value.name in SHAPES:
            old, new = SHAPES[value.name]
            if numpy_helper.to_array(value).tolist() != old:
                raise ValueError('Unexpected downstream reshape')
            value.CopyFrom(numpy_helper.from_array(np.array(new, dtype=np.int64), value.name))
            found.add(value.name)
    if found != set(SHAPES):
        raise ValueError('Missing downstream reshape')

    def sliced(input_name, output_name, start, end, name):
        constants = []
        for suffix, values in (('start',[start]), ('end',[end]), ('axis',[1]), ('step',[1])):
            key = name + '_' + suffix
            model.graph.initializer.append(numpy_helper.from_array(np.array(values,dtype=np.int64),key))
            constants.append(key)
        return helper.make_node('Slice',[input_name]+constants,[output_name],name=name)

    # Full waveform, CQT, global min/max and normalization remain upstream.
    # The largest downstream temporal radius is ten frames (onset via notes).
    # The left retained margin is twenty; the original right boundary is kept.
    normalized = nodes[209].output[0]
    if nodes[210].input[0] != normalized:
        raise ValueError('Unexpected normalized-CQT consumer')
    crop = sliced(normalized,'m3_tail_normalized',CROP_START,CROP_END,'m3_tail_crop')
    nodes[210].input[0] = 'm3_tail_normalized'
    output_slices = []
    for index, name in ((242,'StatefulPartitionedCall:1'),(247,'StatefulPartitionedCall:2')):
        if list(nodes[index].output) != [name] or nodes[index].op_type != 'Reshape':
            raise ValueError('Unexpected final head')
        tail = name + '_tail'
        nodes[index].output[0] = tail
        output_slices.append(sliced(tail,name,READOUT[0]-CROP_START,READOUT[1]+1-CROP_START,
                                    'm3_readout_' + str(index)))
    del model.graph.node[:]
    model.graph.node.extend(nodes[:210]+[crop]+nodes[210:]+output_slices)
    del model.graph.value_info[:]
    for output in model.graph.output:
        shape = output.type.tensor_type.shape.dim
        if len(shape) != 3:
            raise ValueError('Unexpected model output rank')
        shape[1].ClearField('dim_param')
        shape[1].dim_value = 28 if output.name == 'StatefulPartitionedCall:0' else 2
    metadata = {value.key:value.value for value in model.metadata_props}
    metadata.update({'m3.crop.schema':SCHEMA,'m3.crop.parent_sha256':PARENT_SHA256,
                     'm3.crop.original_readout':'164,165'})
    helper.set_model_props(model,metadata)
    if [node.SerializeToString() for node in model.graph.node[:210]] != upstream:
        raise ValueError('Crop modified the full-window front end')
    after = {value.name:value.SerializeToString() for value in model.graph.initializer}
    if any(after[name] != value for name,value in original_initializers.items() if name not in SHAPES):
        raise ValueError('Crop modified model weights or upstream constants')
    onnx.checker.check_model(model,full_check=True)
    destination.parent.mkdir(parents=True,exist_ok=True)
    onnx.save_model(model,destination)
    report = dict(schema=SCHEMA,parent_sha256=PARENT_SHA256,
        derived_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        derived_bytes=destination.stat().st_size,onnx_version=onnx.__version__,
        retained_time_range=[CROP_START,CROP_END],original_readout=list(READOUT),
        output_frames=2,downstream_maximum_temporal_radius=10,
        full_front_end_unchanged=True,weights_unchanged=True,onnx_check_pass=True,
        numerical_identity='not measured by export')
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','destination','report-path'):
        parser.add_argument('--'+name,type=Path,required=True)
    print(json.dumps(export(**vars(parser.parse_args()))))


if __name__=='__main__': main()
