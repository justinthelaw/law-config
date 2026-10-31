import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const { marked } = await import(pathToFileURL(resolve('lib/marked.esm.js')));
const controls = [['*word*','<em>word</em>'], ['a_b_c','a_b_c']];
const extra = [['🙂*a**','🙂<em>a</em>*'], ['_*!a**','_*!a**'],
  ['a\u0301_b_','a\u0301_b_'], ['***foo*bar','**<em>foo</em>bar'],
  ['__****(**__','<strong>****(**</strong>'], ['__ __****_ö**__','__ _<em>****<em>ö**</em></em>']];
const rows = (process.env.PANEL_STAGE === 'preserve' ? controls : extra).map(([source, expected]) =>
  ({source, expected, actual: marked.parseInline(source, {gfm:false})}));
console.log(JSON.stringify(rows));
if (rows.some(x => x.actual !== x.expected)) process.exit(42);
