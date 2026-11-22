"""Execute the unchanged spectral-patch experiment with durable epoch recovery."""
import argparse
import json
from pathlib import Path

from tools.portable_basic_pitch_comparison import check_hash, remote_only
from tools.portable_harmonic_context_learning import run


EXECUTION = dict(
    schema='m3_harmonic_training_recovery_v1',
    scientific_specification='docs/recovery/harmonic-spectral-patches-20261122.json',
    scientific_specification_sha256='dde4de4739f7c72945ef6c07c8b838e30914671b33de2fba9dc0f161936e6479',
    prior_run_id=45006866083,
    prior_run_weights_available=False,
    max_worker_minutes=120,
    max_processing_minutes=105,
    checkpoint_interval='each completed epoch',
    resume_identity='same source, specification, dependencies, inputs, normalization and optimizer settings',
    automatic_redispatch=False,
    scientific_gates_changed=False,
)


def run_recovery(execution_spec, output, resume_checkpoint=None):
    remote_only()
    envelope = json.loads(execution_spec.read_text())
    if envelope != EXECUTION:
        raise ValueError('Frozen recovery execution envelope mismatch')
    root = Path(__file__).resolve().parents[1]
    scientific_spec = root/envelope['scientific_specification']
    check_hash(scientific_spec, envelope['scientific_specification_sha256'])
    return run(scientific_spec, output, training_recovery=envelope,
               resume_checkpoint=resume_checkpoint)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execution-spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume-checkpoint', type=Path)
    result = run_recovery(**vars(parser.parse_args()))
    print(json.dumps(dict(state=result['state'], decision=result['decision'], gates=result['gates'])))
