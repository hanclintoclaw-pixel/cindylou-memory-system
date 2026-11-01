"""A routine checkpoint must not erase the live canary recovery pointer."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('checkpoint',Path(__file__).resolve().parents[2]/'scripts/memory_unification_checkpoint.py')
checkpoint=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checkpoint)


class CheckpointProcessesTests(unittest.TestCase):
    def run_checkpoint(self,extra):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'STATE.json').write_text(json.dumps({'active_processes':[{'pid':123,'label':'existing'}]}))
            argv=['checkpoint','--batch','U4','--status','in_progress','--note','verified',
                  '--next-action','continue']+extra
            with patch.object(checkpoint,'CONTROL',root),patch('sys.argv',argv),contextlib.redirect_stdout(io.StringIO()):
                checkpoint.main()
            return json.loads((root/'STATE.json').read_text())['active_processes']

    def test_ordinary_checkpoint_preserves_live_process(self):
        self.assertEqual(self.run_checkpoint([]),[{'pid':123,'label':'existing'}])

    def test_explicit_replacement_and_shutdown(self):
        self.assertEqual(self.run_checkpoint(['--active-process','{"pid":456,"label":"canary"}']),
                         [{'pid':456,'label':'canary'}])
        self.assertEqual(self.run_checkpoint(['--clear-active-processes']),[])

    def test_malformed_process_cannot_replace_recovery_pointer(self):
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            self.run_checkpoint(['--active-process','{"pid":true}'])
