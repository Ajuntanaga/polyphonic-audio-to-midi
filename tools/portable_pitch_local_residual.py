"""One frozen pitch-local residual screen on the existing GitHub CPU route."""
import argparse
import json
from pathlib import Path

from tools.pitch_local_residual import PARAMETERS, PitchLocalResidual, summarize
from tools.portable_spectral_ablation import run as run_screen


METHOD = dict(schema='m3_pitch_local_residual_v1', parameters=PARAMETERS,
    parameter_key='local_residual_parameters', name='pitch-local-residual',
    model_factory=lambda templates, notes, extractor: PitchLocalResidual(
        templates, notes, extractor.folds, extractor.frequency_hz, extractor.bin_width_hz),
    model_file='frozen-local-residual-model.npz', summarize=summarize,
    distinct='Every pitch receives a local residual-addition test, including globally inactive groups; nuisance fits have no shrinkage penalty.',
    limits=['Nominal harmonic masks can miss detuned partials; no bend or tuning-drift robustness claim.',
            'Shared-harmonic and template-mismatch residuals can still create false pitches.',
            'Candidate support uses fixed nominal masks and fit-fold scaling; no evaluation-fold coefficient or normalization fit.'])


def run(spec_path, output):
    return run_screen(spec_path, output, method=METHOD)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', dest='spec_path', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    result = run(**vars(parser.parse_args()))
    print(json.dumps(dict(state=result['state'], decision=result['decision'], gates=result['gates'])))
