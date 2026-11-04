"""Meaningful negative controls for the fixed synthetic platform boundary."""
import json
from pathlib import Path
import platform
import tempfile
import unittest
from unittest.mock import patch

from unification import confinement as c
from unification.isolation import Rejected


class AdmissionTests(unittest.TestCase):
    def test_default_off_does_not_resolve_input_or_spawn(self):
        with patch.object(c, 'canonical', side_effect=AssertionError('input accessed')), patch.object(c.subprocess, 'Popen', side_effect=AssertionError('spawned')):
            self.assertEqual(c.run_synthetic_confinement('/missing')['reason'], 'default-off-or-real-lane')

    def test_all_real_lanes_denied_before_input_access(self):
        with patch.object(c, 'canonical', side_effect=AssertionError('input accessed')), patch.object(c.subprocess, 'Popen', side_effect=AssertionError('spawned')):
            for lane in ['private-native', 'legacy', 'unified', 'operator', 'session', '']:
                result = c.run_synthetic_confinement('/missing', enabled=True, lane=lane)
                self.assertEqual(result['status'], 'unavailable')
                self.assertFalse(result['real_reader_execution'])

    def test_unsupported_platform_has_no_unsandboxed_fallback(self):
        with patch.object(c.platform, 'system', return_value='Linux'), patch.object(c.subprocess, 'Popen', side_effect=AssertionError('spawned')):
            self.assertEqual(c.run_synthetic_confinement('/missing', enabled=True)['reason'], 'platform-control-unavailable')

    def test_missing_platform_binary_has_no_unsandboxed_fallback(self):
        with patch.object(c.platform, 'system', return_value='Darwin'), patch.object(c, 'SANDBOX', Path('/missing-synthetic-sandbox')), patch.object(c.subprocess, 'Popen', side_effect=AssertionError('spawned')):
            self.assertEqual(c.run_synthetic_confinement('/missing', enabled=True)['status'], 'unavailable')


@unittest.skipUnless(platform.system() == 'Darwin' and c.SANDBOX.is_file(), 'Darwin sandbox required')
class EnforcementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.parent = Path(self.temp.name).resolve()
        self.parent.chmod(0o700)

    def tearDown(self):
        self.temp.cleanup()

    def test_kernel_denies_adversarial_writes_and_descendants_then_settles_timeout(self):
        result = c.run_synthetic_confinement(self.parent, enabled=True)
        self.assertEqual(result['status'], 'synthetic-proof-passed', result)
        self.assertEqual(len(result['controls']['controls']), 11)
        self.assertTrue(all(item['denied'] and item['errno'] in (1, 13) for item in result['controls']['controls']))
        self.assertTrue(result['controls']['allowed_write'])
        self.assertTrue(result['synthetic_protected_preserved'])
        self.assertTrue(result['timeout_child_settled'])
        self.assertTrue(result['active_control']['direct_child_reaped'])
        self.assertFalse(result['production_write_denial_proven'])
        self.assertFalse(result['private_native_available'])
        self.assertEqual(json.loads((Path(result['scratch_root'])/'receipt.json').read_text()), result)

    def test_failed_platform_launch_is_unavailable_and_retained(self):
        with patch.object(c, '_run', side_effect=OSError('synthetic sandbox init failure')):
            result = c.run_synthetic_confinement(self.parent, enabled=True)
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['timeout_control'])
        self.assertIn('synthetic sandbox init failure', result['active_control']['stderr'])
        self.assertTrue((Path(result['scratch_root'])/'receipt.json').is_file())

    def test_healthy_exit_without_enforcement_evidence_cannot_pass(self):
        with patch.object(c, '_run', return_value={'returncode': 0, 'stdout': '{}', 'stderr': '', 'direct_child_reaped': True, 'timed_out': False}) as run:
            result = c.run_synthetic_confinement(self.parent, enabled=True)
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(run.call_count, 1)
        self.assertFalse(result['fork_and_detached_spawn_denied'])

    def test_malformed_output_is_unavailable_not_success(self):
        with patch.object(c, '_run', return_value={'returncode': 0, 'stdout': 'not-json', 'stderr': '', 'direct_child_reaped': True, 'timed_out': False}):
            result = c.run_synthetic_confinement(self.parent, enabled=True)
        self.assertEqual(result['status'], 'unavailable')

    def test_changed_protected_fixture_invalidates_even_claimed_denials(self):
        names = ['overwrite', 'create', 'unlink', 'rename', 'replace', 'chmod',
                 'symlink-write', 'hardlink', 'sidecar', 'fork', 'spawn-detached']
        def fake_run(profile, writable, protected, mode, timeout):
            (protected/'sentinel.txt').write_text('synthetic-change')
            return {'returncode': 0, 'stdout': json.dumps({'allowed_write': True,
                'controls': [{'name': n, 'denied': True} for n in names]}),
                'stderr': '', 'direct_child_reaped': True, 'timed_out': False}
        with patch.object(c, '_run', side_effect=fake_run) as run:
            result = c.run_synthetic_confinement(self.parent, enabled=True)
        self.assertEqual(result['status'], 'unavailable')
        self.assertFalse(result['synthetic_protected_preserved'])
        self.assertEqual(run.call_count, 1)

    def test_timeout_without_kill_and_reap_is_not_settlement(self):
        names = ['overwrite', 'create', 'unlink', 'rename', 'replace', 'chmod',
                 'symlink-write', 'hardlink', 'sidecar', 'fork', 'spawn-detached']
        controls = {'returncode': 0, 'stdout': json.dumps({'allowed_write': True,
            'controls': [{'name': n, 'denied': True} for n in names]}),
            'stderr': '', 'direct_child_reaped': True, 'timed_out': False}
        timeout = {'returncode': None, 'stdout': 'started', 'stderr': '',
                   'direct_child_reaped': False, 'timed_out': True}
        with patch.object(c, '_run', side_effect=[controls, timeout]):
            result = c.run_synthetic_confinement(self.parent, enabled=True)
        self.assertEqual(result['status'], 'unavailable')
        self.assertFalse(result['timeout_child_settled'])

    def test_world_accessible_scratch_parent_rejected_before_dispatch(self):
        self.parent.chmod(0o755)
        with patch.object(c, '_run', side_effect=AssertionError('spawned')), self.assertRaises(Rejected):
            c.run_synthetic_confinement(self.parent, enabled=True)

    def test_symlink_parent_rejected_before_dispatch(self):
        link = self.parent/'link'
        link.symlink_to(self.parent)
        with patch.object(c, '_run', side_effect=AssertionError('spawned')), self.assertRaises(Rejected):
            c.run_synthetic_confinement(link, enabled=True)


if __name__ == '__main__':
    unittest.main()
