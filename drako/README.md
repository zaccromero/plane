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
