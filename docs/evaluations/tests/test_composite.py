import json, sys, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'develop-benchmark/panel'))
import composite
import controller
from composite import identity, verify_component, verify_inventory, qualification_matches, validate_common_component, COMMIT, PACKAGE_SHA256

class CompositeTests(unittest.TestCase):
 def test_identity_preserves_legacy_and_binds_companion(self):
  develop='a'*64
  self.assertEqual(identity({'package_sha256':develop}),develop)
  self.assertNotEqual(identity({'package_sha256':develop,'companion':{'package_sha256':'b'*64}}), identity({'package_sha256':develop,'companion':{'package_sha256':'c'*64}}))
 def test_rejects_altered_package(self):
  with self.assertRaises(ValueError): verify_component(Path(__file__).parent, {'package_sha256':'0'*64})
 def test_qualification_matches_both_directions(self):
  plain={'package_sha256':'a'*64}; combined=dict(plain,companion={'package_sha256':'b'*64})
  legacy={'package_sha256':'a'*64}; newer=dict(legacy,treatment_identity=identity(combined))
  self.assertTrue(qualification_matches(legacy,plain))
  self.assertFalse(qualification_matches(legacy,combined))
  self.assertFalse(qualification_matches(newer,plain))
  self.assertTrue(qualification_matches(newer,combined))
 def test_common_companion_is_prerelease_guard(self):
  c={'source_commit':COMMIT,'package_sha256':PACKAGE_SHA256,'skills':{'x':'y'}}
  spec={'common_companion':{'source_commit':COMMIT,'package_sha256':PACKAGE_SHA256}}
  validate_common_component(spec,{'companion':c},{'companion':c})
  with self.assertRaises(ValueError): validate_common_component(spec,{}, {'companion':c})
  with self.assertRaises(ValueError): validate_common_component(spec,{'companion':c}, {'companion':dict(c,skills={})})
  validate_common_component({}, {}, {'companion':c})
 def test_verified_package_and_tampering(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory); (root/'.codex-plugin').mkdir(); (root/'skills/example').mkdir(parents=True)
   manifest=root/'.codex-plugin/plugin.json'; manifest.write_text(json.dumps({'name':'superpowers','version':'6.3.0','hooks':{}}))
   skill=root/'skills/example/SKILL.md'; skill.write_text('fixture')
   pin={'source':'https://github.com/openai/plugins','source_commit':COMMIT,'source_path':'plugins/superpowers','version':'6.3.0','manifest_sha256':composite.digest(manifest),'package_sha256':composite.package_hash(root),'skills':{'example':composite.digest(skill)}}
   with patch.object(composite,'PACKAGE_SHA256',pin['package_sha256']), patch.object(composite,'MANIFEST_SHA256',pin['manifest_sha256']):
    self.assertEqual(verify_component(root,pin),pin['skills'])
    skill.write_text('altered')
    with self.assertRaises(ValueError): verify_component(root,pin)
 def test_component_set_ignores_label_only(self):
  a={'package_sha256':'a'*64,'label':'one','companion':{'package_sha256':'b'*64}}
  b=dict(a,label='two')
  self.assertNotEqual(identity(a),identity(b))
  self.assertEqual(composite.component_set(a),composite.component_set(b))
 def test_execution_boundary_includes_composite_only_when_used(self):
  with patch.object(controller.E.host,'COMPANION',{'package_sha256':'a'}):
   self.assertEqual(controller.execution_boundary()['composite.py'],composite.digest(Path(composite.__file__)))
  with patch.object(controller.E.host,'COMPANION',None):
   self.assertNotIn('composite.py',controller.execution_boundary())
 def test_rejects_companion_in_control(self):
  with self.assertRaises(ValueError): verify_inventory('control',['superpowers@superpowers-local'],{},Path('/develop'),Path('/companion'),{})
if __name__=='__main__':unittest.main()
