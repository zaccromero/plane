# Scoped coding extension

The original drako_runner is unchanged. This additive runner supports one explicit two-file run-status catalog in its admitted isolated worktree. Native Claude gets exactly five MCP tools: ticket_read, read_context, write_file, run_tests, result. Edit paths, sizes, write count, test attempts, runtime and streamed output are bounded. No general shell, file, GitHub or deployment tools are exposed.

Generated Python runs under a tested per-invocation macOS sandbox-exec profile, with network and unrelated user data denied, writes restricted to test scratch, and credentials removed from its environment. The workload guard runs outside this profile using its existing real host context. This is scoped execution hardening, not a claim of a general hostile-code virtualization boundary.

Immutable independent acceptance tests complement model-authored tests. The parent requires a hash-bound P0/P1-clean review before committing only the two approved files, publishing a branch and opening a PR. Existing RunJournal, native ownership, SSH traces/scores and idempotent evidence remain authoritative. Unknown execution/commit/PR outcomes hold for reconciliation rather than blindly rerunning the model.

Source gate: existing drako_runner README's two documented gates, plus Python3.14 `-B -m unittest discover -s drako_coding -p test_coding.py -v`. After native delivery, fixed independent contract and worker-authored tests must pass under the OS profile. No upstream app source changes or full application build are required for this additive component.

Prepare through drako-coding-runner prepare --config PRIVATE_BINDING --ticket UUID; run DIRECTORY --interrupt-after-execution; after independent host review, resume DIRECTORY. The current catalog requires initially absent drako_status files and a private isolated feature branch. Existing/published output is preserved; reuse requires a newly reconciled catalog/source, not overwriting accepted files. PR merge and owner acceptance remain separate.
