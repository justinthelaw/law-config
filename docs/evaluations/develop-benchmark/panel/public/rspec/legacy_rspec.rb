require 'rspec/core'
mod = Module.new { def fixture_value = 42 }
RSpec.configuration.include mod, selected: true
seen = {}
RSpec.describe("selected example", selected: true) { it("includes") { seen[:selected] = fixture_value } }
RSpec.describe("ordinary example") { it("skips") { seen[:ordinary] = respond_to?(:fixture_value) } }
exit 1 unless RSpec::Core::Runner.run([], $stderr, $stdout) == 0 && seen == {selected: 42, ordinary: false}
