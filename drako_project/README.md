# Fixed real-project qualification adapter

Composes the merged drako_coding engine with one explicitly trusted drako-tools catalog. No global/client permissions change. A target must be a registered isolated drako-tools worktree with the exact Git common-dir/origin and a validated feature branch. The only editable files are reference/guard.reference.js and reference/guard.reference.test.js.

The adapter reuses native subscription/session identity, actor-bound claims, five-tool supervision, baseline/source/runtime pins, sealed delivery, immutable SSH telemetry and idempotent Plane evidence. Only project preparation, context/test specialization and project-fenced publication differ. Parent/stdio server specialize module bindings in their own single-job process; no concurrent jobs or arbitrary project/command arguments are accepted from the model.

Node22 tests use its supported experimental-test-isolation=none mode, a pinned binary, no fork/network, narrow data reads, scratch-only writes, cleared credentials and CPU/output bounds. Independent acceptance is immutable. TAP must contain positive test/pass counts and zero failed/cancelled/skipped/todo cases. Full project canonical npm test is additionally required in hash-bound host review before publication.

Gate: Python3.14 -B -m unittest discover -s drako_project -p test_adapter.py -v. Target project gate is its package.json npm test; research-library workflow is path-scoped and unrelated. Existing merged engine proof is reused for unchanged source. Project PR and adapter PR are reviewable separately; neither is automatically merged. No live bridge/runtime deployment is part of this qualification.
