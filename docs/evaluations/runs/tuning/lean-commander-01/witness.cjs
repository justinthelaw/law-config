const { Command } = require(process.cwd());
function check(declared) {
  const parent = new Command().storeOptionsAsProperties();
  const child = parent.command('sub');
  if (declared) { parent.option('--common <value>'); child.option('--common <value>'); }
  parent.setOptionValueWithSource('common', 'parent', 'config');
  child.setOptionValueWithSource('common', 'child', 'cli');
  const source = child.getOptionValueSourceWithGlobals('common');
  return { source: source === undefined ? null : source, source_is_undefined: source === undefined, value: child.optsWithGlobals().common ?? null };
}
console.log(JSON.stringify({ undeclared: check(false), declared_control: check(true) }));
