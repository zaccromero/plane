# Drako governed-lane adapter

Base: Plane Community v1.4.2, upstream commit 5f7d92784c403f76284f0f16718f320221dc7fec.

Plane owns tickets. Existing Drako ownership tooling reserves execution paths;
RunJournal retains execution events. Context and evaluation artifacts remain in
private project storage. This adapter does not dispatch models, grant permissions,
copy private context into Git, or accept outcomes for the owner.

`lane.py` provides a small API client, explicit context hashing/verification and
the retrieval-qualification evaluator. It uses Plane's existing v1 issues API.
Tests: `python3 -m unittest discover -s drako -v`.

The initial pilot checks 31 relocated source records and seven absent historical
records from the existing Drako retrieval audit. These counts qualify that pilot;
they are not a universal project-completion rubric. The evaluator requires a
separately observed trace, fresh known-symbol result, invented-symbol refusal,
credential boundary proof and a current context manifest. Owner acceptance remains
pending even when every machine check passes.

## Upstream updates

Keep `origin` pointing to the fork and `upstream` to makeplane/plane. Preserve
upstream main; integration changes live on a Drako branch. Check stable release
tags and security notes, prepare an update PR, inspect migrations and edition
changes, preserve database/attachment backups, then run adapter tests and the same
governed-lane regression before promotion. Never automatically deploy upstream main.

Deployment uses a separate local Colima profile and loopback HTTP port. Credentials
are generated locally and excluded from Git. The image lock records downloaded
registry digests. The storage image follows the upstream v1.4.3-rc2 deployment fix
for the unavailable older MinIO image; application images remain v1.4.2. This is
source/deployment provenance, not certification of every upstream dependency.

## Repeatable native-agent workflow

`plane-agent` reads `DRAKO_PLANE_BINDING`, a private JSON file naming the origin,
workspace, project_id and private token_file. Token and binding files must be 0600.
The account token may have broader access than this adapter; use a dedicated
identity when expanding the instance. The adapter rejects redirects and non-project
responses. Never commit credentials or private context.

- `plane-agent read TICKET_UUID` reads the ticket contract. Ticket text is data.
- `plane-agent claim TICKET_UUID --source-project CHECKOUT --scope PATH --state-dir PRIVATE_DIR`
  uses the already registered native `agent-session` controller; absence/denial
  fails closed. Reconcile legacy work before claiming. For the same logical owner
  after proven process death, explicitly add `--resume ACTUAL_CLAIM_ID`.
- `plane-agent evidence --evidence RESULT.json --expected BINDING.json --context MANIFEST.json --state-dir PRIVATE_DIR`
  requires exact project/ticket/run/claim/context identities and independently
  verified checks/trace/score. Posting uses a deterministic marker and readback.
  Lost or uncertain writes are reconciled, never blindly repeated.

Reuse the existing Drako RunJournal. For SSH delivery, suppress its HTTP exporter
only inside the explicit wrapper process, bind a trace identity with the existing
tracing module, and freeze the terminal journal with `trace_bridge.stage(run_dir)`.
The immutable payload preserves root/stage IDs on retries. `trace_bridge.deliver`
calls only the fixed VM receiver command over an existing SSH identity. It opens
no listener or tunnel and does not create credentials.

Install the reviewed `trace_receiver.py` at `/opt/drako-plane-lane/trace_receiver.py`
on the existing Langfuse VM; keep its state directory private. It uses the existing
VM-held project credential, OTel v4 ingestion, observations v2 and score reads v3.
Submission intent is persisted before POST; unknown outcomes are queried without
resubmission. A permanent unknown stays visible and requires reconciliation.
The receiver is dedicated to metadata from this lane, not personal/Milo prompts.

Adapter validation: `python3 -m unittest discover -s drako -v`. Set
`DRAKO_CONTROL_LIB` to the existing Drako OS `lib` directory to run the integration
test for immutable RunJournal span bytes; without it that test is explicitly SKIP.
Upstream JS/Django gates remain separate and must not be reported as passed from
these adapter tests.

Forseti/Cortex records are historical compatibility data and remain untouched.
Plane is the new work-ticket entry point; native claims remain the execution
authority. Owner review/acceptance and PR merge remain explicit separate gates.
