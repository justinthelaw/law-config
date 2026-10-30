import os
from sympy import simplify, symbols
x = symbols("x", real=True)
if os.environ["PANEL_STAGE"] == "contract":
    ranges = ( (x > 2) & (x < 5), (x >= 2) & (x <= 5),
               (x >= 2) & (x < 5), (x > 2) & (x <= 5) )
    expressions = [~r for r in ranges] + [~ranges[0] & ~((x > 7) & (x < 9))]
else:
    expressions = [(x > 1) & (x < 8), x <= 4]
for expr in expressions:
    result = simplify(expr)
    for point in range(11):
        if expr.subs(x, point) != result.subs(x, point):
            print(expr, result, point, expr.subs(x, point), result.subs(x, point))
            raise SystemExit(42)
