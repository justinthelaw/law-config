import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
const original = execFileSync('git', ['show','HEAD:action.yml']);
if (!original.equals(readFileSync('action.yml'))) process.exit(42);
const pkg = JSON.parse(readFileSync('package-lock.json'));
const contents = readFileSync('action.yml','utf8');
if (!contents.includes('dist/index.js') || !pkg.packages?.['node_modules/undici']) process.exit(42);
