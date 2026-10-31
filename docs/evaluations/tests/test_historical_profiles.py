"""Exercise historical hashes and the real paired-input verifier without fresh data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(ROOT/'develop-benchmark/panel')]
import efficiency_pilot as pilot
import export_panel
from test_records import sample, HASH


class HistoricalProfiles(unittest.TestCase):
    def test_historical_hashes_without_confirmation(self):
        program = """import sys
sys.path[:0]=['docs/evaluations/tools','docs/evaluations/develop-benchmark/panel']
import export_panel as X
assert X.E.COHORT is None
assert X.E.PANEL['protocol']=='pr-quality-pytest-entry-natural-v1'
for digest in (X.computation_hash(),X.E.version_digest()):
 assert len(digest)==64 and set(digest)<=set('0123456789abcdef')
print('historical hashes pass')"""
        env = dict(os.environ, DEVELOP_EVAL_COHORT='pr-quality-pytest-entry-natural-v1')
        self.assertIn(b'historical hashes pass', subprocess.check_output(
            [sys.executable, '-B', '-c', program], cwd=ROOT.parent.parent, env=env))

    def test_historical_export_includes_proven_and_missing_arm_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, _ = sample(root)
            case = manifest['cases'][0]
            key, controls = case['id'], case['controls']
            case = dict(case, gold=case['merged'], delta=case['pr_delta'], build='build', native='test')
            ref = dict(admission={}, prompt_sha256=HASH, merged_patch_sha256=HASH, deps_sha256=HASH,
                       workers=controls['workers'], deadline_seconds=controls['deadline_seconds'])
            plan = dict(name='historical', judge_rotations=0, order={key:['control','develop']})
            proof = dict(final_stock=dict(apps=[],mcp=[],global_instructions=[]),
                         inventory=dict(path='inventory.json',sha256=HASH),
                         input=dict(sha256=HASH), final_config_sha256=HASH)
            def attest(name, case, role):
                if role=='develop':raise FileNotFoundError('missing turn-input.json')
                return dict(thread_start=dict(ephemeral=False)), proof
            with patch.object(export_panel.E,'COHORT',None), \
                 patch.dict(export_panel.E.PANEL,protocol='pr-quality-pytest-entry-natural-v1'), \
                 patch.object(export_panel.C,'run_dir',return_value=root), \
                 patch.object(export_panel.C,'verify_receipt',return_value=dict(fingerprint=HASH)), \
                 patch.object(export_panel.E,'read',return_value=dict(plugins=[])), \
                 patch.object(export_panel.D,'compare',return_value={}), \
                 patch.object(pilot,'check_input',side_effect=attest) as check:
                result = export_panel.portable_case(dict(pairs={},evaluator_cost=[],pr_open_to_merge_seconds=1),
                    case, ref, plan, dict(queues=[[key]],cpu_pairs=[[0,1]]))
            self.assertEqual(check.call_count, 2)
            profiles = result['comparison']['profiles']
            self.assertIsNone(profiles['develop'])
            self.assertEqual(profiles['control'], dict(proof['final_stock'],plugins=[],
                inventory_sha256=HASH,turn_sha256=HASH,config_sha256=HASH,ephemeral=False))
            self.assertNotIn('confirmation', result['comparison'])

    def test_real_attester_rejects_different_prompt_before_native_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arm = root/'attempts/pytest/control'
            arm.mkdir(parents=True)
            (arm/'inventory.json').write_text('{}')
            turn = dict(threadId='root', effort=pilot.E.PANEL['effort'], input=[dict(type='text',text='different task')])
            (arm/'turn-input.json').write_text(json.dumps(turn))
            with patch.object(pilot.C,'run_dir',return_value=root), patch.object(pilot.E,'COHORT',None), \
                 patch.object(pilot.C,'read_attempt',return_value=dict(state='completed',root='root')), \
                 patch.object(pilot.C.controller,'STOCK') as native:
                with self.assertRaisesRegex(ValueError,'paired model input'):
                    pilot.check_input('historical','pytest','control')
                native.assert_not_called()


if __name__=='__main__': unittest.main()
