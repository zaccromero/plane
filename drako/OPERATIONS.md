# Drako Plane: running it and not losing it

Plane is the board for work and deadlines. Its data lives only in a Postgres volume inside
the dedicated Colima profile `drako-plane`, so it needs to be up and it needs a copy.

## Start, stop

```bash
drako/ops/plane-up.sh            # start the profile and the existing containers; waits for :8097
colima stop --profile drako-plane
```

`plane-up.sh` starts only what already exists. It never creates containers, pulls images or
touches another Colima profile.

## Always on, backed up nightly (owner, once)

```bash
sh drako/ops/install.sh
```

Installs `ai.drako.plane` (runs `plane-up` at login and every 15 minutes; a no-op when the
board answers) and `ai.drako.plane-backup` (03:30 daily). Dumps go to
`~/.local/state/drako-plane/backups/plane-<UTC>.sql.gz`, newest 14 kept, mode 0600. A dump
without the issues table is discarded and the job exits non-zero. The VM takes 6 GB of RAM
while running.

## Restore

Into a scratch database first, to prove the dump before trusting it:

```bash
db="$(docker --context colima-drako-plane ps --format '{{.ID}} {{.Image}} {{.Names}}' | awk '$2 ~ /postgres/ && $3 ~ /db/ {print $1; exit}')"
gzip -dc ~/.local/state/drako-plane/backups/plane-<UTC>.sql.gz | docker --context colima-drako-plane exec -i "$db" sh -c 'PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -w -U "${POSTGRES_USER:-postgres}" -d postgres'
```

`pg_dumpall` output recreates roles and databases; restoring over a live instance replaces
it. Stop the API containers first and take a fresh dump before any real restore.

## Importing Cortex

See `cortex_import.py`. Take a backup first, then dry run, then a three-record canary:

```bash
drako/ops/plane-backup.sh
python3 drako/cortex_import.py --binding ~/.config/drako-plane/binding.json
python3 drako/cortex_import.py --binding ~/.config/drako-plane/binding.json --apply --limit 3
python3 drako/cortex_import.py --binding ~/.config/drako-plane/binding.json --apply
```

The runner (`drako-map-runner queue`) only works tickets passed to it by id with `--ticket`;
it has no listing call, so imported Backlog issues are never picked up on their own.
