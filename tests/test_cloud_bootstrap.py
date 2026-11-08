import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cloud.kaggle.recover_corpus import run


class CloudBootstrapTests(unittest.TestCase):
    def test_input_failure_produces_final_report_before_any_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                run(root, root / 'missing-inputs')
            report = json.loads((root / 'bootstrap-report.json').read_text())
            self.assertEqual(report['state'], 'failed')
            self.assertTrue(report['final'])
            self.assertEqual(report['completed_stages'], [])

    def test_failed_replay_preserves_successful_build_and_test_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            failure = subprocess.CalledProcessError(1, ['replay'])
            with patch('cloud.kaggle.recover_corpus.prepare_source', return_value=(root, root, root / 'manifest')), \
                 patch('cloud.kaggle.recover_corpus.subprocess.run', side_effect=[None, None, None, failure]), \
                 patch('builtins.print'):
                with self.assertRaises(subprocess.CalledProcessError):
                    run(root, root)
            report = json.loads((root / 'bootstrap-report.json').read_text())
            self.assertEqual(report['completed_stages'], [0, 1, 2])
            self.assertEqual(report['stage'], 3)
            self.assertEqual(report['log'], 'stage-3.log')
            self.assertEqual(report['returncode'], 1)
            self.assertTrue(report['final'])
            self.assertFalse(report['promotion_accepted'])


if __name__ == '__main__':
    unittest.main()
