#!/bin/sh
# Prove Plane can be recovered and can come back on its own. Owner-run.
#
#   restore   Load the newest dump into a THROWAWAY Postgres container (no ports, removed
#             afterwards) and compare its issue counts with the live board. The live
#             database is never written.
#   cold      Stop the drako-plane VM and let the ai.drako.plane LaunchAgent bring it back.
#             Plane, and Mission Control's tasks and deadlines, are down meanwhile.
#   all       restore, then cold.
set -eu
PROFILE="${DRAKO_PLANE_PROFILE:-drako-plane}"
CTX="colima-$PROFILE"
DIR="${DRAKO_PLANE_BACKUP_DIR:-$HOME/.local/state/drako-plane/backups}"
URL="${DRAKO_PLANE_URL:-http://127.0.0.1:8097/}"
DRILL="plane-restore-drill"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

count() { # count <container> <database> <sql>
  docker --context "$CTX" exec "$1" sh -c "PGPASSWORD=\"\${POSTGRES_PASSWORD:-}\" psql -w -U \"\${POSTGRES_USER:-postgres}\" -d $2 -tAc \"$3\""
}

restore() {
  dump="$(ls -1t "$DIR"/plane-*.sql.gz 2>/dev/null | head -1)"
  [ -n "$dump" ] || { echo "drill: no dump in $DIR" >&2; exit 1; }
  echo "drill: restoring $(basename "$dump") into a throwaway container"
  live="$(docker --context "$CTX" ps --format '{{.ID}} {{.Image}} {{.Names}}' | awk '$2 ~ /postgres/ && $3 ~ /db/ {print $1; exit}')"
  [ -n "$live" ] || { echo "drill: live Plane database not running" >&2; exit 1; }
  image="$(docker --context "$CTX" inspect -f '{{.Config.Image}}' "$live")"
  docker --context "$CTX" rm -f "$DRILL" >/dev/null 2>&1 || true
  docker --context "$CTX" run -d --rm --pull never --name "$DRILL" -e POSTGRES_HOST_AUTH_METHOD=trust "$image" >/dev/null
  trap 'docker --context "$CTX" stop "$DRILL" >/dev/null 2>&1 || true' EXIT
  # The image initialises with a temporary server, then restarts; wait for the real one.
  i=0; until docker --context "$CTX" logs "$DRILL" 2>&1 | grep -q 'PostgreSQL init process complete' \
      && docker --context "$CTX" exec "$DRILL" pg_isready -q -U postgres 2>/dev/null; do
    i=$((i+1)); [ "$i" -lt 60 ] || { echo "drill: scratch database did not start" >&2; exit 1; }; sleep 1; done
  err="$(mktemp)"
  gzip -dc "$dump" | docker --context "$CTX" exec -i "$DRILL" psql -q -U postgres -d postgres >/dev/null 2>"$err" || true
  sql="select count(*) || '|' || count(*) filter (where external_source='drako-cortex') from issues"
  got="$(docker --context "$CTX" exec "$DRILL" psql -U postgres -d plane -tAc "$sql" 2>/dev/null || echo 'none')"
  want="$(count "$live" plane "$sql" 2>/dev/null || echo 'unknown')"
  echo "drill: restored issues|cortex = $got   live = $want"
  real="$(grep -c 'ERROR' "$err" || true)"; echo "drill: psql errors during restore: $real (role/owner errors are expected for a cluster dump)"
  rm -f "$err"
  docker --context "$CTX" stop "$DRILL" >/dev/null; trap - EXIT
  [ "$got" = "$want" ] && [ "$got" != "none" ] && echo "drill: RESTORE PASS" || { echo "drill: RESTORE FAIL" >&2; exit 1; }
}

cold() {
  echo "drill: stopping $PROFILE (Plane goes down now)"
  colima stop --profile "$PROFILE"
  start="$(date +%s)"
  launchctl kickstart -k "gui/$(id -u)/ai.drako.plane"
  i=0; until curl -fsS -o /dev/null --max-time 3 "$URL"; do
    i=$((i+1)); [ "$i" -lt 100 ] || { echo "drill: COLD START FAIL, $URL not answering after 5 min; see ~/Library/Logs/drako-plane.err.log" >&2; exit 1; }; sleep 3; done
  echo "drill: COLD START PASS, answering after $(( $(date +%s) - start ))s"
}

case "${1:-all}" in
  restore) restore ;;
  cold) cold ;;
  all) restore; cold ;;
  *) echo "usage: $0 [restore|cold|all]" >&2; exit 64 ;;
esac
