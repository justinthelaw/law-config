require "rspec/mocks"
require "rspec/mocks/example_methods"
extend RSpec::Mocks::ExampleMethods
module FixtureOwner; VALUE = 19; end
place=FixtureOwner.const_source_location(:VALUE)
RSpec::Mocks.setup
stub_const("FixtureOwner::VALUE", 31)
exit 42 if FixtureOwner::VALUE!=31
RSpec::Mocks.teardown
exit 42 if FixtureOwner::VALUE!=19
if ENV.fetch("PANEL_STAGE")=="contract"
  current=FixtureOwner.const_source_location(:VALUE)
  puts [place,current].inspect
  exit 42 unless current==place
end
