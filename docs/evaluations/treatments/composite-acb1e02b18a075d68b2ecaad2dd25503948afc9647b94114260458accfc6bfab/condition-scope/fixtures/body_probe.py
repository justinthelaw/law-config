"""Four public body calls; warning attribution is isolated by operation."""
import json
import warnings

try:
    import werkzeug
    from werkzeug import Response
    assert werkzeug.__file__.startswith('/work/src/werkzeug/')
except Exception as error:
    print(json.dumps({'outcome': 'setup-error', 'error': type(error).__name__}))
    raise SystemExit(70)

rows = []
for name, body, mixed in [('strings', ['x', 'y'], False),
                          ('bytes', [b'x', b'y'], False),
                          ('bytes-strings', [b'x', 'y'], True),
                          ('strings-bytes', ['x', b'y'], True)]:
    row = {'input': name, 'operations': []}
    response = None
    for operation in ('get_data', 'close'):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            try:
                if operation == 'get_data':
                    response = Response(body)
                    row['bytes'] = list(response.get_data())
                elif response is not None:
                    response.close()
            except Exception as error:
                row['error'] = type(error).__module__ + '.' + type(error).__qualname__
        row['operations'].append({'operation': operation, 'warnings': [
            {'class': w.category.__module__ + '.' + w.category.__qualname__,
             'filename': w.filename, 'line': w.lineno, 'message': str(w.message)} for w in caught]})
    classes = [w['class'] for op in row['operations'] for w in op['warnings']]
    body_classes = [w['class'] for w in row['operations'][0]['warnings']]
    row['pass'] = (not row.get('error') and row.get('bytes') == [120, 121]
                   and (bool(body_classes) if mixed else not classes)
                   and all(c == 'builtins.DeprecationWarning' for c in classes))
    rows.append(row)
passed = all(row['pass'] for row in rows)
print(json.dumps({'outcome': 'green' if passed else 'red-behavior', 'rows': rows}))
raise SystemExit(0 if passed else 42)
