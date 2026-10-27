import assert from "node:assert/strict";
import {mock,test} from "node:test";
import * as original from "node:fs/promises";
test("pinned Node module mock intercepts a builtin without touching a target",async()=>{
  mock.module("node:fs/promises",{namedExports:{lstat:async()=>"synthetic"}});
  const f=await import("node:fs/promises");assert.equal(await f.lstat("/not-a-real-target"),"synthetic");
  assert.notEqual(f.lstat,original.lstat);
});
