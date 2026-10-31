import os, warnings
from collections import UserList
from werkzeug.wrappers import Response
response = Response([b"a", b"bc"])
if os.environ["PANEL_STAGE"] == "preserve":
    ok = response.get_data() == b"abc" and response.calculate_content_length() == 3
else:
    class SizedStream:
        closed = False
        def __len__(self): return 2
        def __iter__(self): return iter([b"a", b"bc"])
        def close(self): self.closed = True
    stream = SizedStream()
    streamed = Response(stream)
    initial = streamed.is_streamed and not streamed.is_sequence
    streamed.make_sequence()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Response([b"a", "x"]).get_data()
        _ = Response().stream
    ok = (Response(UserList([b"x"])).is_sequence and initial and stream.closed
          and streamed.get_data() == b"abc" and sum(issubclass(w.category, DeprecationWarning) for w in caught) >= 2)
print("response controls", ok)
raise SystemExit(0 if ok else 42)
