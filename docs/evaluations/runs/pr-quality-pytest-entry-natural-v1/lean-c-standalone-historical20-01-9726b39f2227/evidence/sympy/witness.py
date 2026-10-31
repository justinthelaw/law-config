import json
from sympy import Plane, Point3D

plane = Plane((0, 0, 0), normal_vector=(0, 0, 3))
results = {}
for name, point, expected in [
    ('tuple_on_plane', (1, 1, 0), 0),
    ('point_on_plane', Point3D(1, 1, 0), 0),
    ('point_off_plane', Point3D(1, 1, -8), 8),
]:
    try:
        actual = plane.distance(point)
        results[name] = {'value': str(actual), 'expected': expected, 'pass': bool(actual == expected)}
    except Exception as exc:
        results[name] = {'exception': type(exc).__name__, 'message': str(exc), 'expected': expected, 'pass': False}
print(json.dumps(results, sort_keys=True))
raise SystemExit(0 if all(row['pass'] for row in results.values()) else 1)
