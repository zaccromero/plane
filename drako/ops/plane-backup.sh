#!/bin/sh
# Dump the Plane Postgres database to a dated file on the Mac, outside the VM, and keep
# the newest KEEP dumps. Reads the database user from the container's own environment,
# so no credential is stored here or printed.
set -eu
PROFILE="${DRAKO_PLANE_PROFILE:-drako-plane}"
OUT="${DRAKO_PLANE_BACKUP_DIR:-$HOME/.local/state/drako-plane/backups}"
KEEP="${DRAKO_PLANE_BACKUP_KEEP:-14}"
CTX="colima-$PROFILE"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
umask 077
mkdir -p "$OUT"

colima status --profile "$PROFILE" >/dev/null 2>&1 || { echo "plane-backup: profile $PROFILE is not running; nothing dumped" >&2; exit 1; }
# The database container: a postgres image, preferring the one actually named as the db.
db="$(docker --context "$CTX" ps --format '{{.ID}} {{.Image}} {{.Names}}' | awk '$2 ~ /postgres/ {if ($3 ~ /db/) {print $1; found=1; exit} if (!first) first=$1} END {if (!found && first) print first}')"
[ -n "$db" ] || { echo "plane-backup: no running Postgres container in $PROFILE" >&2; exit 1; }

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
tmp="$OUT/.plane-$stamp.sql.gz.partial"
# Credentials come from the database container's own environment. -w never prompts: a
# missing password fails the job instead of hanging an unattended run on "Password:".
docker --context "$CTX" exec "$db" sh -c 'PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}" exec pg_dumpall -w -U "${POSTGRES_USER:-${PGUSER:-postgres}}"' </dev/null | gzip > "$tmp" || true
# A dump that is empty or lacks the issues table is a failure, not a backup.
gzip -dc "$tmp" | grep -q 'CREATE TABLE public.issues' || { rm -f "$tmp"; echo "plane-backup: dump has no issues table; discarded" >&2; exit 1; }
mv "$tmp" "$OUT/plane-$stamp.sql.gz"
ls -1t "$OUT"/plane-*.sql.gz | tail -n +"$((KEEP+1))" | while read -r old; do rm -f "$old"; done
echo "plane-backup: $OUT/plane-$stamp.sql.gz ($(wc -c < "$OUT/plane-$stamp.sql.gz" | tr -d ' ') bytes)"
