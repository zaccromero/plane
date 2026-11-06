# Bounded automatic Plane runner

One explicitly selected ticket uses the immutable-span-check catalog. The native Claude subscription client receives exactly three run-local MCP capabilities, with empty argument schemas: ticket_read, approved_check, result. No general shell, file, browser or delegation tools are granted. Existing managed permissions and hooks remain active.

Python is pinned to /opt/homebrew/bin/python3 (3.14), including the MCP child and approved test. Runtime fingerprints, ticket context, source revision and source-file digests are checked before execution and recovery. Private configuration and run files contain local bindings; never commit them.

Prepare with `drako-plane-runner prepare --config ~/.config/drako-plane/runner.json --ticket UUID`, then run the returned project .drako/runs/run_ID directory. `resume DIRECTORY` publishes completed execution without rerunning the model or test. A live or uncertain execution is held for reconciliation; it is never automatically retried. `run DIRECTORY --interrupt-after-execution` exits 86 at the durable boundary for a recovery exercise.

Bounds: one native invocation, one approved check, 180 seconds, eight assistant messages, six tool calls and 1 MiB streamed output. The approved command runs only drako/test_stage.py under the existing workload guard. Native ownership is sealed then settled only after positive process-group exit. Backend trace/score readback and idempotent Plane evidence precede Owner Review. Owner acceptance remains separate.

Source gate (Python 3.14): `DRAKO_CONTROL_LIB=/Users/zaccromero/code/.worktrees/drako-os/main-canonical/lib /opt/homebrew/bin/python3 -B -m unittest discover -s drako -v`, followed by the same command with `-s drako_runner`. No upstream application source is changed.
