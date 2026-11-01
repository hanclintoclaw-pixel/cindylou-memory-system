"""Installed boundary must stay off, fixed-input and fail closed on code drift."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('canary_install', ROOT/'scripts/memory_unification_canary_install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class CanaryInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registry = self.root/'registry.json'
        self.registry.write_text('deliberately invalid registry')
        self.partition = self.root/'partition'
        self.partition.mkdir()
        (self.partition/'partition.json').write_text('{}')
        self.receipt = installer.install(ROOT,'HEAD',self.registry,self.partition,self.root/'releases',self.root/'bin')
        self.command = Path(self.receipt['command'])

    def invoke(self, *args):
        return subprocess.run([str(self.command),*args], cwd='/', capture_output=True,text=True,timeout=10)

    def test_disabled_before_invalid_inputs_and_after_enabled_failure(self):
        self.assertEqual(self.invoke('health').returncode,2)
        result = self.invoke('--enable-canary','health')
        self.assertEqual(result.returncode,5)
        self.assertEqual(json.loads(result.stdout)['status'],'unavailable')
        self.assertEqual(self.invoke('health').returncode,2)

    def test_input_override_and_abbreviation_refused(self):
        for option in ('--registry','--partition','--reg','--part'):
            with self.subTest(option=option):
                result = self.invoke('--enable-canary',option,'/unapproved','health')
                self.assertEqual(result.returncode,2)
                self.assertNotIn('Traceback',result.stderr)

    def test_modified_release_never_imported(self):
        release = Path(self.receipt['release'])
        (release/'unification/canary_cli.py').write_text('raise RuntimeError("MUST NOT EXECUTE")')
        result = self.invoke('--enable-canary','health')
        self.assertEqual(result.returncode,5)
        self.assertEqual(json.loads(result.stdout)['reason'],'installed release integrity failure')
        self.assertNotIn('MUST NOT EXECUTE',result.stderr)

    def test_existing_command_not_replaced(self):
        before = self.command.read_bytes()
        with self.assertRaises(FileExistsError):
            installer.install(ROOT,'HEAD',self.registry,self.partition,self.root/'other-releases',self.root/'bin')
        self.assertEqual(self.command.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
