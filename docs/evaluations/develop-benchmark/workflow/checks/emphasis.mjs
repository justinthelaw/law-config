import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
const { marked } = await import(pathToFileURL(resolve('lib/marked.esm.js')));
const cases = [
  ['***.x*', '**<em>.x</em>'], ['**(word)*', '*<em>(word)</em>'],
  ['a*b**', 'a*b**'], ['x a*b** y', 'x a*b** y'], ['__(_*', '__(_*'],
  ['*word*', '<em>word</em>'], ['**word**', '<strong>word</strong>'],
  ['a_b_c', 'a_b_c'],
];
// Gold regresses on these two examples. Measure agreement independently of the parity gates.
const extra = [
  ['__****(**__', '<strong>****(**</strong>'],
  ['__ __****_ö**__', '__ _<em>****<em>ö**</em></em>'],
];
const matches = extra.map(([source, expected]) => marked.parseInline(source, { gfm: false }) === expected);
console.log('BENCH_DIAGNOSTIC ' + JSON.stringify({ commonmark_extra: matches }));

for (const [input, expected] of cases) {
  const actual = marked.parseInline(input);
  if (actual !== expected) {
    console.error({ input, expected, actual });
    process.exit(42);
  }
}
