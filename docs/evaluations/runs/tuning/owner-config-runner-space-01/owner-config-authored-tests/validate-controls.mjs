// Assessor only. This file is never copied into any participant/source tree.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import YAML from '/deps/check-tools/node_modules/yaml/dist/index.js';
const input = JSON.parse(fs.readFileSync('/evidence/controls.json', 'utf8'));
const oldPin = 'actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97';
const newPin = 'actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0';
const parse = ([workflow, hooks]) => ({workflow: YAML.parse(workflow), hooks: YAML.parse(hooks)});
const clone = value => structuredClone(value);
const owner = value => {
  const job = value.workflow.jobs['pre-commit'];
  assert(!Object.hasOwn(job, 'if'), 'owning job condition requires separate semantic verification');
  const selected = job.steps.map((step, index) => [step, index]).filter(([step]) => step.name === 'Setup Python');
  assert.equal(selected.length, 1);
  const [step, index] = selected[0];
  assert(!Object.hasOwn(step, 'if'), 'owning setup condition requires separate semantic verification');
  assert.equal(step.with['python-version'], '3.15');
  const repos = value.hooks.repos.filter(repo => repo.repo === 'https://github.com/DavidAnson/markdownlint-cli2');
  assert.equal(repos.length, 1);
  assert.equal(repos[0].hooks.filter(hook => hook.id === 'markdownlint-cli2').length, 1);
  return {job, step, index, repo: repos[0]};
};
const requested = parse(input.controls.requested);
const active = owner(requested);
assert.equal(active.step.uses, newPin);
assert.equal(active.repo.rev, 'v0.24.0');
const original = parse(input.original);
const originalOwner = owner(original);
assert([oldPin, newPin].includes(originalOwner.step.uses));
assert(['v0.23.3', 'v0.24.0'].includes(originalOwner.repo.rev));
originalOwner.step.uses = newPin;
originalOwner.repo.rev = 'v0.24.0';
assert.deepEqual(original, requested, 'requested transform changed unrelated semantics');
for (const [name, bytes] of Object.entries(input.controls)) {
  const expected = clone(requested);
  const selected = owner(expected);
  if (name === 'old-active-no-decoy' || name === 'wrong-inactive-decoy') selected.step.uses = oldPin;
  if (name === 'wrong-inactive-decoy') selected.job.steps.push({name: 'Unrelated disabled Python pin', if: '${{ false }}', uses: newPin, with: {'python-version': '3.15'}});
  if (name === 'harmless-empty-env') {
    assert(!Object.hasOwn(selected.step, 'env'), 'neutral env already exists');
    selected.step.env = {};
  }
  if (name === 'old-markdownlint') selected.repo.rev = 'v0.23.3';
  assert.deepEqual(parse(bytes), expected, 'control semantic mismatch: ' + name);
}
console.log(JSON.stringify({status: 'verified', controls: Object.keys(input.controls), active_job: 'pre-commit', active_step: 'Setup Python', markdown_repository: active.repo.repo}));
