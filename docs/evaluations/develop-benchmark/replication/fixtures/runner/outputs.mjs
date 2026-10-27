import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {dirname,resolve} from "node:path";
import {test} from "node:test";
import vm from "node:vm";

const original=JSON.parse(await readFile("/fixtures/public-keys.json","utf8"));
function keys(body,start,end) {
  const section=body.split(start+":\n")[1]?.split("\n"+end+":\n")[0]??"";
  return [...section.matchAll(/^  ([a-z][a-z0-9-]+):$/gm)].map(x=>x[1]).sort();
}
test("public input and output names match the frozen action contract",async()=>{
  const body=await readFile("/work/action.yml","utf8");
  assert.deepEqual(keys(body,"inputs","outputs"),original.inputs);
  assert.deepEqual(keys(body,"outputs","runs"),original.outputs);
});

// Evaluate only compiled orchestration/reporting text in a separate VM. The VM
// has no process, shell, module loader, filesystem implementation or real adapter.
// Every package/builtin and every adapter is supplied explicitly. A new blocked
// import is a fixture compatibility condition, not a failed product behavior.
test("failed operations reach the public output while cleanup remains best effort",async()=>{
  const context=vm.createContext(Object.create(null)),out=new Map(),failed=[],warn=[],events=[];
  const ctx={platform:"linux",architecture:"x64",isContainer:false,isGitHubHosted:true,isDefinitionCompatibleImage:true,hasPasswordlessSudo:false};
  const plan={profile:"custom",enabled:new Set(),skipped:new Set()};
  const fakeOperations=["failed","removed","failed","not-found"].map((status,i)=>({id:"synthetic-"+i,run:async()=>({status})}));
  const readings=[100n,145n];
  const deps=new Map([
    ["@actions/core",{info(){},warning:s=>warn.push(s),setFailed:s=>failed.push(s),setOutput:(k,v)=>{events.push(k);out.set(k,String(v));}}],
    ["node:fs/promises",{statfs:async()=>({bavail:readings.shift(),bsize:1n})}],
    ["/work/build/src/components.js",{COMPONENTS:[]}],
    ["/work/build/src/planner.js",{createPlan:()=>plan}],
    ["/work/build/src/inputs.js",{readActionInput:()=>""}],
    ["/work/build/src/runtime.js",{createRuntimeContext:async()=>ctx}],
    ["/work/build/src/platforms/linux.js",{createLinuxAdapter:async()=>({supportedComponents:new Set(),operations:async()=>fakeOperations})}],
    ["/work/build/src/platforms/macos.js",{createMacOSAdapter:async()=>{throw Error("wrong platform");}}],
    ["/work/build/src/platforms/windows.js",{createWindowsAdapter:async()=>{throw Error("wrong platform");}}],
    ["/work/build/src/operations.js",{
       prepareOperations:ops=>ops,executeOperations:ops=>Promise.all(ops.map(op=>op.run())),
       createUnsupportedOperation:()=>{throw Error("unexpected unsupported operation");}
    }],
  ]);
  const modules=new Map();
  async function moduleFor(name) {
    if(modules.has(name))return modules.get(name);
    let m;
    if(deps.has(name)) {
      const exports=deps.get(name);
      m=new vm.SyntheticModule(Object.keys(exports),function(){for(const [n,v]of Object.entries(exports))this.setExport(n,v);},{context,identifier:name});
    } else {
      if(!name.startsWith("/work/build/src/")||!name.endsWith(".js"))throw Error("FIXTURE_BOUNDARY_UNOBSERVED blocked VM import "+name);
      m=new vm.SourceTextModule(await readFile(name,"utf8"),{context,identifier:name});
    }
    modules.set(name,m);return m;
  }
  const m=await moduleFor("/work/build/src/index.js");
  await m.link((s,from)=>moduleFor(s.startsWith(".")?resolve(dirname(from.identifier),s):s));
  await m.evaluate({timeout:2000});
  // The historical main launches its promise without exporting it.
  // Yield host turns for synthetic promises to finish.
  for(let i=0;i<20 && events.length<original.outputs.length && failed.length===0;i++) await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(failed,[]);
  assert.deepEqual(Object.fromEntries(out),{"available-bytes-before":"100","available-bytes-after":"145","reclaimed-bytes":"45","failed-operations":"2","platform":"linux","architecture":"x64"});
  assert.equal(events.length,original.outputs.length);
});
