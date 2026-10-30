import { readFileSync, lstatSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
const { parse } = createRequire('/deps/check-tools/package.json')('yaml');
const read = file => readFileSync(file, 'utf8');
const job = parse(read('.github/workflows/lint.yml')).jobs['pre-commit'];
const steps = job.steps;
const staticallyFalse = value => value === false || (typeof value === 'string'
  && /^(?:false|\$\{\{\s*false\s*\}\})$/i.test(value.trim()));
const setup = steps.filter(step => step.uses?.startsWith('actions/setup-python@'));
const hooks = parse(read('.pre-commit-config.yaml')).repos.filter(entry =>
  entry.repo === 'https://github.com/DavidAnson/markdownlint-cli2');
const ledgerPaths = [
  ...execFileSync('git', ['diff', '--name-only', '-z', 'HEAD', '--', 'docs/dependency-upgrades'], { encoding: 'utf8' }).split('\0'),
  ...execFileSync('git', ['ls-files', '--others', '--exclude-standard', '-z', '--', 'docs/dependency-upgrades'], { encoding: 'utf8' }).split('\0'),
];
const original = {
  'action.yml': 'fede0d5cdf225b3d9bb14e444e7d7debc95e4c62',
  'package.json': '216b3e748df717eb0d3710e47659d297555af5c9',
  'package-lock.json': 'da7820ef41d2346d5478ab56359ee9fa4e842907',
  'dist/index.js': '171f696b772012b91066efacc71a939fea76c6da',
};
const checks = [
  setup.length === 1 && setup[0].uses === 'actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0'
    && setup[0].with?.['python-version'] === '3.15' && !staticallyFalse(job.if) && !staticallyFalse(setup[0].if),
  hooks.length === 1 && hooks[0].rev === 'v0.24.0' && hooks[0].hooks.some(h => h.id === 'markdownlint-cli2'),
  ledgerPaths.some(file => file.endsWith('.md') && lstatSync(file, { throwIfNoEntry: false })?.isFile() && read(file).trim()),
  Object.entries(original).every(([file, id]) => execFileSync('git', ['hash-object', file], { encoding: 'utf8' }).trim() === id),
];
if (checks.includes(false)) { console.error(checks); process.exit(42); }
