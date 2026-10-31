#define FMT_HEADER_ONLY
#include <fmt/chrono.h>
#include <iostream>
#include <limits>
int main() {
  auto finite = fmt::format("{:%S %S}", std::chrono::duration<double>(-61.25));
  auto infinite = fmt::format("{:%S %Q}", std::chrono::duration<double>(-std::numeric_limits<double>::infinity()));
  std::cout << finite << "\n" << infinite << "\n";
  return finite == "-01.250000 01.250000" && infinite == "-inf inf" ? 0 : 42;
}
