#include "CLI/CLI.hpp"
#include <cmath>
#include <complex>
#include <cstdlib>
#include <iostream>
#include <string>
bool parses(const char* text, std::complex<double> expected) {
    CLI::App app;
    std::complex<double> result{};
    app.add_option("--value",result);
    const char* args[] = {"app","--value",text};
    try { app.parse(3,args); }
    catch(const CLI::ParseError&) { return false; }
    std::cout << text << " -> " << result << '\n';
    return std::abs(result-expected) < 1e-9;
}
int main() {
    if (std::string(std::getenv("PANEL_STAGE")) == "preserve")
        return parses("2+3i",{2,3}) && parses("1e-4",{0.0001,0}) ? 0 : 42;
    return parses("3+4e-3i",{3,0.004}) && parses("-1E-2-2E-1j",{-0.01,-0.2})
        && parses("5e-4i",{0,0.0005}) ? 0 : 42;
}
