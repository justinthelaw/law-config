import os
from sympy import Plane, Point3D, Segment3D, Ray3D, Line3D, symbols
plane = Plane((0, 0, 0), normal_vector=(0, 0, 3))
if os.environ["PANEL_STAGE"] == "preserve":
    ok = plane.distance(Point3D(1, 1, -8)) == 8 and plane.distance((1, 1, 0)) == 0
else:
    a, b = symbols("a b", real=True)
    start, end = Point3D(1, 0, a), Point3D(4, 1, b)
    try:
        segment = plane.distance(Segment3D(start, end))
        ray = plane.distance(Ray3D(start, end))
        line = plane.distance(Line3D(start, end))
        ok = all(expr.subs({a:x,b:y}) == expected for expr,x,y,expected in
                 [(segment,5,7,5),(segment,-3,6,0),(ray,-4,-6,4),(ray,-4,3,0),
                  (line,2,7,0),(line,2,2,2)])
    except (ValueError, TypeError, NotImplementedError) as error:
        print(type(error).__name__, error); ok = False
print("geometry", ok)
raise SystemExit(0 if ok else 42)
