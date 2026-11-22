import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

from tools.portable_artifact_subset import digest, extract_selected, run, validate_files


class ArtifactSubsetTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = b'{"events":[{"pitch":60}]}\n'
        self.files = {'arm/ordinary-events.json': dict(bytes=len(self.data),
            sha256=hashlib.sha256(self.data).hexdigest())}
        self.archive = self.root/'source.zip'
        with zipfile.ZipFile(self.archive, 'w') as bundle:
            bundle.writestr('arm/ordinary-events.json', self.data)
            bundle.writestr('large-model.npz', b'not selected')

    def test_exact_selected_bytes_only(self):
        result = extract_selected(self.archive, digest(self.archive), self.files, self.root/'out')
        self.assertEqual(result, self.files)
        self.assertEqual((self.root/'out/arm/ordinary-events.json').read_bytes(), self.data)
        self.assertFalse((self.root/'out/large-model.npz').exists())

    def test_hash_failures_write_nothing(self):
        with self.assertRaisesRegex(ValueError, 'Archive SHA256'):
            extract_selected(self.archive, '0'*64, self.files, self.root/'out')
        bad = json.loads(json.dumps(self.files))
        bad['arm/ordinary-events.json']['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'Selected file SHA256'):
            extract_selected(self.archive, digest(self.archive), bad, self.root/'out')
        self.assertFalse((self.root/'out').exists())

    def test_rejects_unsafe_names_and_duplicate_members(self):
        for name in ('../events.json', '/events.json', 'arm//events.json', 'arm\\events.json'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_files({name: next(iter(self.files.values()))})
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.archive, 'a') as bundle:
                bundle.writestr('arm/ordinary-events.json', self.data)
        with self.assertRaisesRegex(ValueError, 'duplicated'):
            extract_selected(self.archive, digest(self.archive), self.files, self.root/'out')
        self.assertFalse((self.root/'out').exists())

    def test_remote_guard_precedes_all_file_access(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {}, clear=True), self.assertRaisesRegex(RuntimeError, 'GitHub Actions only'):
            run(self.root/'missing-spec.json', self.root/'out')
        self.assertFalse((self.root/'out').exists())


if __name__ == '__main__':
    unittest.main()
