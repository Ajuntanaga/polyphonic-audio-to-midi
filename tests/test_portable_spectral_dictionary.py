"""Synthetic orchestration: either held-out failure prevents continuous replay."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import portable_spectral_dictionary as runner


class PortableDictionaryTests(unittest.TestCase):
    def test_either_held_out_failure_skips_continuous_replay(self):
        class Model:
            def __init__(self, templates, notes):
                self.weights = np.ones(2)
                self.design = np.ones((2,200))
                self.r = np.eye(200)
                self.projector = np.ones((200,2))
                self.notes = np.asarray(notes)
                self.cutoff = None
            def activity(self, features):
                return np.zeros((len(features),53))
        for gate_sequence in ([True,False,True], [True,True,False]):
            with self.subTest(gates=gate_sequence), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                refs = {}
                for name in ('sources','baseline'):
                    path = root/(name+'.json')
                    path.write_text('{}')
                    refs[name] = dict(path=str(path), sha256=runner.digest(path))
                spec = root/'spec.json'
                spec.write_text(json.dumps(dict(worker_repository='example/worker',
                    mixture_and_clock_settings=runner.SETTINGS,
                    dictionary_parameters=runner.PARAMETERS, references=refs, input_releases=[],
                    datasets=dict(ordinary={}, **{'extended-middle':{}}))))
                plan = [dict(note=60, source_key=str(i)) for i in range(200)]
                with ExitStack() as stack:
                    stack.enter_context(patch.object(runner,'remote_only'))
                    stack.enter_context(patch.object(runner,'captured_text',return_value='a'*40))
                    stack.enter_context(patch.dict(runner.os.environ, dict(SOURCE_SHA='a'*40,
                        GITHUB_REPOSITORY='example/worker',GITHUB_SHA='b'*40,
                        GITHUB_RUN_ID='synthetic',GITHUB_RUN_ATTEMPT='1')))
                    stack.enter_context(patch.object(runner.scipy,'__version__','1.13.1'))
                    stack.enter_context(patch.object(runner.np,'__version__','1.26.4'))
                    stack.enter_context(patch.object(runner,'validate_manifest',
                        return_value=([],dict(train=200,calibration=200,test=155))))
                    stack.enter_context(patch.object(runner,'template_plan',return_value=plan))
                    stack.enter_context(patch.object(runner,'source_waves',return_value={}))
                    stack.enter_context(patch.object(runner,'build_templates',return_value=np.ones((2,200))))
                    stack.enter_context(patch.object(runner,'DictionaryModel',Model))
                    stack.enter_context(patch.object(runner,'role_examples',
                        return_value=(np.zeros((3,2)),np.zeros((3,53),dtype=bool),{})))
                    stack.enter_context(patch.object(runner,'fit_training_cutoff',
                        return_value=dict(cutoff=.5,feasible=True)))
                    stack.enter_context(patch.object(runner,'representation_gate',side_effect=gate_sequence))
                    replay = stack.enter_context(patch.object(runner,'continuous_dataset'))
                    result = runner.run(spec,root/'output')
                replay.assert_not_called()
                self.assertEqual(result['state'],'completed')
                self.assertTrue(result['final'])
                self.assertFalse(result['continuous_replay']['executed'])
                self.assertFalse(result['research_screen_passed'])
                self.assertEqual(result['datasets'],{})
                self.assertEqual(set(result['mixtures']),{'train','calibration','test'})
                self.assertTrue(result['frozen_model']['persisted_before_held_out_scoring'])


if __name__ == '__main__':
    unittest.main()
