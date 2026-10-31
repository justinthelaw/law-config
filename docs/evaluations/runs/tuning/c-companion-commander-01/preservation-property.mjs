import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
const { Command } = await import(pathToFileURL(resolve(process.argv[2], 'index.js')));
const states = [
  { id:'absent', declared:false }, { id:'declared-unset', declared:true },
  ...[undefined,false,'',0,'value'].map(value => ({id:'unknown-'+String(value),declared:true,set:true,value,source:undefined})),
  ...['default','config','env','cli','implied'].map(source => ({id:source+'-value',declared:true,set:true,value:'value',source})),
  {id:'config-undefined',declared:true,set:true,value:undefined,source:'config'},
  {id:'cli-empty',declared:true,set:true,value:'',source:'cli'},
];
const own = (value,key) => Object.hasOwn(value,key);
const encoded = value => value === undefined ? {undefined:true} : value;
function check(configuration, storage) {
  const commands=[];
  for (let i=0;i<configuration.length;i++) {
    const cmd = i ? commands[i-1].command('level'+i) : new Command('root');
    cmd.storeOptionsAsProperties(storage[i]);
    if (configuration[i].declared) cmd.option('--mode <value>');
    if (configuration[i].set) cmd.setOptionValueWithSource('mode',configuration[i].value,configuration[i].source);
    commands.push(cmd);
  }
  const leaf=commands.at(-1);
  // The rootmost public opts() owner wins the global merge, including own undefined values.
  const winner=commands.findIndex(cmd => own(cmd.opts(),'mode'));
  const values=leaf.optsWithGlobals();
  const expectedSource=winner<0 ? undefined : commands[winner].getOptionValueSource('mode');
  const expectedValue=winner<0 ? undefined : commands[winner].opts().mode;
  assert.equal(own(values,'mode'),winner>=0);
  assert.equal(values.mode,expectedValue);
  const actualSource=leaf.getOptionValueSourceWithGlobals('mode');
  return {pass:Object.is(actualSource,expectedSource),winner,expectedValue:encoded(expectedValue),expectedSource:encoded(expectedSource),actualSource:encoded(actualSource),states:configuration.map(s=>s.id),storeAsProperties:storage};
}
let total=0,failures=0;const examples=[];const counts={};const failureClasses={};const ownerDepth={};
for (const depth of [2,3]) {
  function enumerate(configuration) {
    if(configuration.length<depth){for(const state of states)enumerate([...configuration,state]);return;}
    for(let bits=0;bits<(1<<depth);bits++){
      const storage=configuration.map((_,i)=>Boolean(bits&(1<<i)));
      const result=check(configuration,storage);total++;
      const category=depth+'-level';counts[category]??={cases:0,failures:0};counts[category].cases++;
      if(!result.pass){failures++;counts[category].failures++;const reason=configuration[result.winner].id==='declared-unset'&&storage[result.winner]?'declared-unset-property-winner-unknown-source':'explicit-unknown-source-winner';failureClasses[reason]=(failureClasses[reason]??0)+1;const owner=depth+'-level/winner-index-'+result.winner;ownerDepth[owner]=(ownerDepth[owner]??0)+1;if(examples.length<4)examples.push(result);}
    }
  }
  enumerate([]);
}
// Discriminating controls use only public methods, not private source-map expectations.
const known=check([states.find(s=>s.id==='config-value'),states.find(s=>s.id==='cli-value')],[false,false]);
const childOnly=check([states[0],states.find(s=>s.id==='cli-value')],[false,false]);
assert(known.pass && childOnly.pass);
const observedUnknown=check([states.find(s=>s.id==='unknown-value'),states.find(s=>s.id==='cli-value')],[false,false]);
const declaredProperty=check([states[1],states.find(s=>s.id==='cli-value')],[true,false]);
assert.notEqual(known.expectedSource,'cli'); // Deliberately wrong leaf-only selector is discriminated by the known parent control.
console.log(JSON.stringify({total,failures,counts,failureClasses,ownerDepth,examples,controls:{knownParent:known,childOnly,unknownParent:observedUnknown,declaredPropertyParent:declaredProperty},oracle:'Rootmost own key in public opts() must supply both optsWithGlobals value and getOptionValueSourceWithGlobals source; explicit undefined remains an own value. No arbitrary source strings/private state mutation.'}));
