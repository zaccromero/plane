#!/bin/sh
# Bring the local Drako Plane board up. Starts only what already exists: the dedicated
# Colima profile and the Compose containers already created inside it. Creates nothing,
# pulls nothing, never touches another Colima profile.
set -eu
PROFILE="${DRAKO_PLANE_PROFILE:-drako-plane}"
URL="${DRAKO_PLANE_URL:-http://127.0.0.1:8097/}"
CTX="colima-$PROFILE"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

colima status --profile "$PROFILE" >/dev/null 2>&1 || colima start --profile "$PROFILE"

up() { curl -fsS -o /dev/null --max-time 3 "$URL"; }
i=0
while [ "$i" -lt 20 ]; do up && { echo "plane-up: $URL answering"; exit 0; }; i=$((i+1)); sleep 3; done

# The VM is up but the board is not: start the existing Compose containers.
ids="$(docker --context "$CTX" ps -aq --filter label=com.docker.compose.project)"
[ -n "$ids" ] || { echo "plane-up: no Compose containers exist in profile $PROFILE; see OPERATIONS.md" >&2; exit 1; }
# shellcheck disable=SC2086
docker --context "$CTX" start $ids >/dev/null
i=0
while [ "$i" -lt 40 ]; do up && { echo "plane-up: $URL answering"; exit 0; }; i=$((i+1)); sleep 3; done
echo "plane-up: containers started but $URL is not answering" >&2
exit 1
