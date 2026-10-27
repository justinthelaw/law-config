import assert from "node:assert/strict";
import { mock, test } from "node:test";
import * as fs from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

// One disposable root per scenario. All commands are simulated. A replacement
// is renamed into position while the original still exists at a distinct path,
// so this exercise cannot depend on inode reuse.
let live;
const denied = () => Object.assign(new Error("synthetic ordinary remove denied"), {code:"EACCES"});
const existing = async path => { try { await fs.lstat(path); return true; } catch(e) { if(e.code==="ENOENT") return false; throw e; } };
const inside = p => typeof p==="string" && live && resolve(p).startsWith(live.root+"/");
const assertHook = (observed, name) => assert.ok(observed, "FIXTURE_BOUNDARY_UNOBSERVED "+name);
const wrapped = {};
for(const [name, value] of Object.entries(fs)) if(name!=="default") wrapped[name]=value;
wrapped.lstat=async (p,...opts) => {
  const result=await fs.lstat(p,...opts);
  if(live && p===live.target && live.switchAt==="after-observation" && !live.switched) await live.swap();
  return result;
};
for(const name of ["rm","unlink"]) wrapped[name]=async(p,...opts) => {
  assert.ok(inside(p),"synthetic fixture allows removal only under its active root");
  if(p===live.target) {
    live.removeCalls++;
    if(live.switchAt==="after-denial" && !live.switched) await live.swap();
    if(live.denial) throw denied();
    if(live.noop) return;
  }
  return fs[name](p,...opts);
};
mock.module("node:fs/promises",{defaultExport:wrapped,namedExports:wrapped,cache:true});
const cmds=pathToFileURL("/work/build/src/command.js");
mock.module(cmds,{cache:true,namedExports:{
  runElevated:async(_context,_command,args) => {
    assert.ok(live && args.at(-1)===live.target && inside(live.target),"refuse an unrelated elevated target");
    live.elevated++;
    if(live.elevatedEffect==="remove") await fs.rm(live.target,{recursive:true,force:true});
    return {exitCode:0,stdout:"",stderr:""};
  },
  runCommand:async()=>{throw Error("non-simulated command request")},commandExists:async()=>false,findCommandPath:async()=>undefined,
  TRUSTED_UNIX_PATH:"/usr/bin:/bin:/usr/sbin:/sbin",UNIX_SUDO_EXECUTABLE:"/usr/bin/sudo",
}});
const {removePathTarget,createRemovePathOperation,executeOperations}=await import("/work/build/src/operations.js");
const context={platform:"linux",architecture:"x64",home:"/home/runner",temp:"/home/runner/work/_temp",workspace:"/home/runner/project",runtimeExecutable:"/tools/node",actionPath:"/work",isContainer:false,isGitHubHosted:true,isDefinitionCompatibleImage:true,isUbuntuSlim:false,hasPasswordlessSudo:true};
async function fixture({initial="directory",replacement="directory",...options}={}) {
  const root=await fs.mkdtemp("/tmp/runner-contract-"),target=join(root,"selection"),safe=join(root,"referent"),spare=join(root,"original-held");
  await fs.mkdir(safe);await fs.writeFile(join(safe,"sentinel"),"untouched");
  async function make(kind,label) {
    if(kind==="directory") {await fs.mkdir(target);await fs.writeFile(join(target,"sentinel"),label);}
    else if(kind==="link") await fs.symlink(safe,target);
  }
  await make(initial,"original");
  live={root,target,safe,elevated:0,removeCalls:0,switched:false,...options,
    swap:async()=>{await fs.rename(target,spare); await make(replacement,"replacement");live.switched=true;}};
  return {...live,run:()=>removePathTarget(target,[root],context),
    verifySafe:async()=>assert.equal(await fs.readFile(join(safe,"sentinel"),"utf8"),"untouched"),
    verifyReplacement:async()=>{assertHook(live.switched,"target replacement");assert.equal((await fs.lstat(target)).isSymbolicLink(),replacement==="link");if(replacement==="directory") assert.equal(await fs.readFile(join(target,"sentinel"),"utf8"),"replacement");}};
}
test("stable directory is removed normally",async()=>{
  const f=await fixture();assert.equal((await f.run()).status,"removed");assert.equal(await existing(f.target),false);assert.equal(live.elevated,0);
});
test("stable final link is unlinked without traversing its referent",async()=>{
  const f=await fixture({initial:"link"});assert.equal((await f.run()).status,"removed");assert.equal(await existing(f.target),false);await f.verifySafe();assert.equal(live.elevated,0);
});
test("absent target is reported without a retry",async()=>{
  const f=await fixture({initial:"absent"});assert.equal((await f.run()).status,"not-found");assert.equal(live.elevated,0);
});
for(const [label,initial,replacement] of [["same-kind","directory","directory"],["kind-changing","directory","link"]]) {
  test("rejects "+label+" replacement after initial observation before removal",async()=>{
    const f=await fixture({initial,replacement,switchAt:"after-observation"});
    const outcome=await f.run();assertHook(live.switched,"lstat");
    assert.equal(outcome.status,"failed");await f.verifyReplacement();await f.verifySafe();assert.equal(live.elevated,0);
  });
}
for(const [label,initial,replacement] of [["directory","directory","directory"],["link","link","directory"]]) {
  test("rejects replacement after refused ordinary "+label+" removal before elevated retry",async()=>{
    const f=await fixture({initial,replacement,switchAt:"after-denial",denial:true,elevatedEffect:"noop"});
    const outcome=await f.run();assertHook(live.switched,"ordinary refusal");assert.equal(outcome.status,"failed");
    assert.equal(live.elevated,0);await f.verifyReplacement();await f.verifySafe();
  });
}
test("an unchanged target can be removed by the mocked elevated retry",async()=>{
  const f=await fixture({denial:true,elevatedEffect:"remove"});assert.equal((await f.run()).status,"removed");assert.equal(live.elevated,1);assert.equal(await existing(f.target),false);
});
test("ordinary successful return with a surviving target reports failure",async()=>{
  const f=await fixture({noop:true});const result=await f.run();assertHook(live.removeCalls>0,"ordinary no-op");assert.equal(result.status,"failed");assert.equal(await existing(f.target),true);
});
test("elevated successful return with a surviving target reports failure",async()=>{
  const f=await fixture({denial:true,elevatedEffect:"noop"});const result=await f.run();assertHook(live.elevated>0,"mocked elevated no-op");assert.equal(result.status,"failed");assert.equal(await existing(f.target),true);
});
test("partial failures keep result order and allow independent targets to finish",async()=>{
  const f=await fixture({noop:true});
  const targets=[join(f.root,"one"),f.target,join(f.root,"absent"),join(f.root,"four")];
  await fs.mkdir(targets[0]);await fs.mkdir(targets[3]);
  const ops=targets.map((target,i)=>createRemovePathOperation({id:"op-"+i,component:"dotnet",description:"fixture operation "+i,target,allowedParents:[f.root],context}));
  const rows=await executeOperations(ops);assertHook(live.removeCalls>0,"ordered no-op");
  assert.deepEqual(rows.map(r=>r.status),["removed","failed","not-found","removed"]);
  assert.deepEqual(await Promise.all(targets.map(existing)),[false,true,false,false]);await f.verifySafe();
});
