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
db="$(docker --context "$CTX" ps --format '{{.ID}} {{.Image}}' | awk '$2 ~ /postgres/ {print $1; exit}')"
[ -n "$db" ] || { echo "plane-backup: no running Postgres container in $PROFILE" >&2; exit 1; }

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
tmp="$OUT/.plane-$stamp.sql.gz.partial"
docker --context "$CTX" exec "$db" sh -c 'pg_dumpall -U "$POSTGRES_USER"' | gzip > "$tmp"
# A dump that is empty or lacks the issues table is a failure, not a backup.
gzip -dc "$tmp" | grep -q 'CREATE TABLE public.issues' || { rm -f "$tmp"; echo "plane-backup: dump has no issues table; discarded" >&2; exit 1; }
mv "$tmp" "$OUT/plane-$stamp.sql.gz"
ls -1t "$OUT"/plane-*.sql.gz | tail -n +"$((KEEP+1))" | while read -r old; do rm -f "$old"; done
echo "plane-backup: $OUT/plane-$stamp.sql.gz ($(wc -c < "$OUT/plane-$stamp.sql.gz" | tr -d ' ') bytes)"
