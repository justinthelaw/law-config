#include "CLI/CLI.hpp"
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

int main() {
    auto range = CLI::Range(0.0, 1.0);
    bool contract = std::string(std::getenv("PANEL_STAGE")) == "contract";
    for (auto entry : {std::string("0"), std::string("0.5"), std::string("1"), std::string("2"), std::string("nan"), std::string("NaN")}) {
        bool nan = entry == "nan" || entry == "NaN";
        if (!contract && nan) continue;
        auto text = entry;
        bool valid = range(text).empty();
        if (valid != (!nan && entry != "2")) {
            std::cout << entry << " accepted=" << valid << "\n";
            return 42;
        }
    }
    return 0;
}
