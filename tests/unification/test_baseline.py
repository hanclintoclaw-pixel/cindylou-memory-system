import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('baseline', Path(__file__).resolve().parents[2]/'scripts/memory_unification_baseline.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class BaselineTests(unittest.TestCase):
    def test_verifier_detects_corruption_not_just_its_own_success(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root/'fact.md'; p.write_text('original')
            manifest = {'files':[{'source':str(p),'snapshot':p.name,'sha256':baseline.digest(p)}],
                        'databases':[],'errors':[],'missing':[]}
            (root/'manifest.json').write_text(json.dumps(manifest))
            self.assertTrue(baseline.verify(root)['ok'])
            p.write_text('corrupted')
            self.assertFalse(baseline.verify(root)['ok'])

    def test_dream_sources_included_but_sidecars_and_runtime_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in ['memory/.dreams/session-corpus/note.md','memory/dreaming/day.md',
                         'memory/._day.md','runtime/transcript.md','.git/private.md']:
                p=root/name; p.parent.mkdir(parents=True,exist_ok=True);p.write_text('x')
            names = [str(p.relative_to(root)) for p in baseline.selected(root,'workspace')]
            self.assertEqual(names,['memory/.dreams/session-corpus/note.md','memory/dreaming/day.md'])


if __name__ == '__main__':
    unittest.main()
