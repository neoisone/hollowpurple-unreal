import json
import tempfile
import unittest
from pathlib import Path

from pipeline import exchange


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'Exchange With Spaces'

    def test_each_transfer_uses_fresh_files_and_unreal_folder(self):
        first = exchange.prepare('blender-to-unreal', self.root, 'SM_Cube', 'Cube')
        second = exchange.prepare('blender-to-unreal', self.root, 'SM_Cube', 'Cube')
        self.assertNotEqual(first['job_dir'], second['job_dir'])
        self.assertNotEqual(first['unreal_destination'], second['unreal_destination'])
        for job in (first, second):
            folder = Path(job['job_dir'])
            self.assertTrue((folder / 'source.py').is_file())
            self.assertTrue((folder / 'target.py').is_file())
            self.assertFalse(Path(job['file']).exists())

    def test_object_names_and_paths_are_python_data_not_injected_code(self):
        source = 'Cube\');raise RuntimeError("injected")#'
        job = exchange.prepare('blender-to-unreal', self.root, 'SM_Test', source)
        for filename in ('source.py', 'target.py'):
            compile((Path(job['job_dir']) / filename).read_text(), filename, 'exec')
        self.assertEqual(json.loads((Path(job['job_dir']) / 'job.json').read_text())['source'], source)

    def test_bad_asset_names_and_unreal_source_paths_fail_before_writing(self):
        for name in ('../bad', 'two words', '', '1bad'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                exchange.prepare('blender-to-unreal', self.root, name, 'Cube')
        with self.assertRaises(ValueError):
            exchange.prepare('unreal-to-blender', self.root, 'SM_Test', 'not-an-asset-path')
        self.assertFalse(self.root.exists())

    def test_verify_requires_export_then_records_size_and_hash(self):
        job = exchange.prepare('unreal-to-blender', self.root, 'SM_Test', '/Game/Test/SM_Test.SM_Test')
        folder = Path(job['job_dir'])
        with self.assertRaises(FileNotFoundError):
            exchange.verify(folder)
        Path(job['file']).write_bytes(b'abc')
        report = exchange.verify(folder)
        self.assertEqual(report['bytes'], 3)
        self.assertEqual(report['sha256'], 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
        self.assertEqual(json.loads((folder / 'job.json').read_text())['sha256'], report['sha256'])

    def test_verify_does_not_accept_an_export_changed_after_verification(self):
        job = exchange.prepare('blender-to-unreal', self.root, 'SM_Test', 'Cube')
        Path(job['file']).write_bytes(b'first')
        exchange.verify(Path(job['job_dir']))
        Path(job['file']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            exchange.verify(Path(job['job_dir']))


if __name__ == '__main__':
    unittest.main()
