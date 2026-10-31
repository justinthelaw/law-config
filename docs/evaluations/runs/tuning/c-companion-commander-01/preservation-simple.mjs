import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
const { Command } = await import(pathToFileURL(resolve("index.js")));
const parent = new Command().storeOptionsAsProperties().option("--common <value>");
const child = parent.command("sub").option("--common <value>");
child.setOptionValueWithSource("common", "child", "cli");
parent.common = "parent";
console.log(JSON.stringify({ value: child.optsWithGlobals().common,
  source: child.getOptionValueSourceWithGlobals("common") ?? null }));
