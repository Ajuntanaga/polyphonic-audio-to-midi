"""Synthetic orchestration of fail-closed training/held-out/continuous gates."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import portable_spectral_ablation as runner


class PortableAblationTests(unittest.TestCase):
    def test_training_or_either_held_out_failure_prevents_continuous(self):
        class Model:
            def __init__(self, templates, notes, folds):
                self.weights = np.ones(2)
                self.design = np.ones((2,200))
                self.notes = np.asarray(notes)
                self.folds = np.asarray(folds)
                self.nnls_calls = 0
                self.cutoff = None
            def activity(self, features):
                return np.zeros((len(features),53))
        class Extractor:
            names = ['one','two']
            folds = np.array([0,1])
        for sequence in ([False],[True,False,True],[True,True,False]):
            with self.subTest(gates=sequence),tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                refs = {}
                for name in ('sources','baseline','source_consistency'):
                    path = root/(name+'.json')
                    path.write_text('{}')
                    refs[name] = dict(path=str(path),sha256=runner.digest(path))
                spec = root/'spec.json'
                spec.write_text(json.dumps(dict(worker_repository='example/worker',
                    mixture_and_clock_settings=runner.SETTINGS,ablation_parameters=runner.PARAMETERS,
                    references=refs,input_releases=[],datasets=dict(ordinary={},middle={}))))
                plan = [dict(note=60,source_key=str(i)) for i in range(200)]
                with ExitStack() as stack:
                    stack.enter_context(patch.object(runner,'remote_only'))
                    stack.enter_context(patch.object(runner,'captured_text',return_value='a'*40))
                    stack.enter_context(patch.dict(runner.os.environ,dict(SOURCE_SHA='a'*40,
                        GITHUB_REPOSITORY='example/worker',GITHUB_SHA='b'*40,
                        GITHUB_RUN_ID='synthetic',GITHUB_RUN_ATTEMPT='1')))
                    stack.enter_context(patch.object(runner.scipy,'__version__','1.13.1'))
                    stack.enter_context(patch.object(runner.np,'__version__','1.26.4'))
                    stack.enter_context(patch.object(runner,'validate_manifest',return_value=([],dict(train=200,calibration=200,test=155))))
                    stack.enter_context(patch.object(runner,'template_plan',return_value=plan))
                    stack.enter_context(patch.object(runner,'source_waves',return_value={}))
                    stack.enter_context(patch.object(runner,'build_templates',return_value=np.ones((2,200))))
                    stack.enter_context(patch.object(runner,'CrossfitAblation',Model))
                    stack.enter_context(patch.object(runner,'AveragedPower',Extractor))
                    examples = stack.enter_context(patch.object(runner,'role_examples',return_value=(np.zeros((3,2)),np.zeros((3,53),bool),{})))
                    stack.enter_context(patch.object(runner,'fit_training_cutoff',return_value=dict(cutoff=.5,feasible=True)))
                    stack.enter_context(patch.object(runner,'complete_chord_gate',side_effect=sequence))
                    replay = stack.enter_context(patch.object(runner,'continuous_dataset'))
                    result = runner.run(spec,root/'output')
                replay.assert_not_called()
                self.assertEqual(examples.call_count,len(sequence))
                self.assertEqual(result['state'],'completed')
                self.assertTrue(result['final'])
                self.assertFalse(result['continuous_replay']['executed'])
                self.assertFalse(result['research_screen_passed'])
                self.assertEqual(set(result['mixtures']),{'train'} if len(sequence)==1 else {'train','calibration','test'})
                self.assertTrue(result['frozen_model']['persisted_before_held_out_scoring'])
                self.assertEqual(result['held_out_scoring']['executed'],len(sequence)==3)


if __name__ == '__main__':
    unittest.main()
