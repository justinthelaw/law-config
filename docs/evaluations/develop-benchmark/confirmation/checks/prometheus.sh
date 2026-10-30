set -eu
if [ "$PANEL_STAGE" = preserve ]; then name=TestPush; else name=TestPushPathSegments; fi
if go test -count=1 -run "^$name$" -v ./prometheus/push >/tmp/probe-log 2>&1; then
  cat /tmp/probe-log
  grep -q -- "--- PASS: $name" /tmp/probe-log
else
  cat /tmp/probe-log
  if grep -q -- "--- FAIL: $name" /tmp/probe-log && grep -Eq '%20|a\+b' /tmp/probe-log; then exit 42; fi
  exit 1
fi
