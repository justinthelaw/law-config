import { readFileSync, readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
const { parse } = createRequire('/deps/check-tools/package.json')('yaml');
const read = file => readFileSync(file, 'utf8');
const steps = parse(read('.github/workflows/lint.yml')).jobs['pre-commit'].steps;
const setup = steps.filter(step => step.uses?.startsWith('actions/setup-python@'));
const hooks = parse(read('.pre-commit-config.yaml')).repos.filter(entry =>
  entry.repo === 'https://github.com/DavidAnson/markdownlint-cli2');
const ledgers = readdirSync('docs/dependency-upgrades').filter(file => file.endsWith('.md'))
  .map(file => read('docs/dependency-upgrades/' + file));
const original = {
  'action.yml': 'fede0d5cdf225b3d9bb14e444e7d7debc95e4c62',
  'package.json': '216b3e748df717eb0d3710e47659d297555af5c9',
  'package-lock.json': 'da7820ef41d2346d5478ab56359ee9fa4e842907',
  'dist/index.js': '171f696b772012b91066efacc71a939fea76c6da',
};
const checks = [
  setup.length === 1 && setup[0].uses.endsWith('@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0')
    && setup[0].with?.['python-version'] === '3.15',
  hooks.length === 1 && hooks[0].rev === 'v0.24.0' && hooks[0].hooks.some(h => h.id === 'markdownlint-cli2'),
  ledgers.some(s => s.split('\n').some(line => line.includes('actions/setup-python') && line.includes('7.1.0'))
    && s.split('\n').some(line => line.includes('markdownlint-cli2') && line.includes('0.24.0'))
    && s.split('\n').some(line => /defer|hold|unchanged|retain|keep/i.test(line)
      && /undici|checkout|setup-node|@types\/node|pre-commit-hooks/i.test(line))),
  Object.entries(original).every(([file, id]) => execFileSync('git', ['hash-object', file], { encoding: 'utf8' }).trim() === id),
];
if (checks.includes(false)) { console.error(checks); process.exit(42); }
