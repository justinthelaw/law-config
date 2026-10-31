"""Measure public MIME matching on novel long inputs and preserve ordinary parsing."""
import os
from statistics import median
from time import process_time_ns

from werkzeug.datastructures import MIMEAccept
from werkzeug.http import parse_cookie


def match_time(length, seed):
    start = process_time_ns()
    for attempt in range(12):
        mime = 'text/plain; profile="a' + " " * length + f'b{seed}-{attempt}"'
        assert MIMEAccept([(mime, 1.0)]).best_match([mime]) == mime
    return (process_time_ns() - start) / 12


if os.environ["PANEL_STAGE"] == "preserve":
    assert parse_cookie('first="a b"; second=2')["first"] == "a b"
    accept = MIMEAccept([("text/plain; charset=UTF-8", 1.0), ("image/*", 0.8)])
    assert accept.best_match(["image/png", "text/plain;charset=UTF-8"]) == "text/plain;charset=UTF-8"
else:
    # With four times as much whitespace, allow up to twice the linear growth.
    # Reverse the sample order and use fresh values so caches cannot mask scanning.
    samples = {512: [], 2048: []}
    for run in range(5):
        order = (512, 2048) if run % 2 == 0 else (2048, 512)
        for length in order:
            samples[length].append(match_time(length, run))
    factor = median(samples[2048]) / median(samples[512])
    print("Fourfold input CPU ratio", factor, samples)
    raise SystemExit(0 if factor <= 8 else 42)
