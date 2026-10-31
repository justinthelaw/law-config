# Run a long check

Start a noninteractive check once. In Codex code mode, keep the terminal waits inside one cell. Replace the example command with the project check.

```js
// @exec: {"yield_time_ms": 300000}
let result = await tools.exec_command({cmd: "make test", yield_time_ms: 1000});
let output = result.output.slice(-6000);
while (result.exit_code == null && result.session_id != null) {
  result = await tools.write_stdin({
    session_id: result.session_id, chars: "", yield_time_ms: 300000
  });
  output = (output + result.output).slice(-6000);
}
text({exit_code: result.exit_code, output});
```

Use a short initial cell yield if independent work is ready. If the cell yields, use `functions.wait` with its cell ID and a long wait. For a command already running, use its existing terminal handle. With direct shell tools, wait on that handle. Keep full logs in the task's scratch directory when needed. Treat a lost handle or missing exit status as incomplete.
