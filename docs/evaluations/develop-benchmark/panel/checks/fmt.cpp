#define FMT_HEADER_ONLY
#include "fmt/chrono.h"
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <string>
int main() {
    using duration = std::chrono::duration<double>;
    if (std::string(std::getenv("PANEL_STAGE")) == "preserve")
        return fmt::format("{:%M}", std::chrono::seconds(180)) == "03" ? 0 : 42;
    auto x = fmt::format("{:%S %Q}", duration(-62.5));
    auto y = fmt::format("{:%Q %S}", duration(-std::numeric_limits<double>::infinity()));
    std::cout << x << " | " << y << '\n';
    return x == "-02.500000 62.5" && y == "-inf inf" ? 0 : 42;
}
