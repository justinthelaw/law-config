import { pathToFileURL } from 'node:url';
const {marked}=await import(pathToFileURL(process.cwd()+'/lib/marked.esm.js'));
const nested=process.env.PANEL_STAGE==='contract';
const actual=marked.parse(nested?'![**left *right***](sample.png)':'![left right](sample.png)').trim();
console.log(actual);
if(actual!=='<p><img src="sample.png" alt="left right"></p>')process.exit(42);
