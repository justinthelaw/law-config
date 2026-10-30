require 'rspec/core'
if ENV["PANEL_STAGE"] == "preserve"
  local = Module.new { def stable = 13 }
  RSpec.configuration.include local, tagged: true
  a = RSpec.describe("tagged", tagged: true)
  b = RSpec.describe("ordinary")
  ok = a.new.stable == 13 && !b.new.respond_to?(:stable)
else
  extension = Module.new { def declared_value = 17 }
  seen = []
  RSpec.configuration.extend extension, tagged: true
  RSpec.shared_context("uses extension") { seen << declared_value }
  RSpec.configuration.include_context "uses extension", tagged: true
  begin
    RSpec.describe("uses shared context", tagged: true)
    RSpec.describe("unrelated")
    ok = seen == [17]
  rescue NameError => error
    warn error.message
    ok = false
  end
end
exit(ok ? 0 : 42)
