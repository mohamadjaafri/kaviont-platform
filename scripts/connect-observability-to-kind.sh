#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

if ! docker network inspect kind >/dev/null 2>&1; then
  echo "The kind Docker network is not present. Keeping the standalone Compose observability stack unchanged."
  exit 0
fi

for service in prometheus blackbox-exporter; do
  container_id="$(docker compose --profile observability ps -q "${service}")"
  if [[ -z "${container_id}" ]]; then
    echo "Compose service ${service} is not running. Start it with 'make observability-up'." >&2
    exit 1
  fi

  networks="$(docker inspect --format '{{json .NetworkSettings.Networks}}' "${container_id}")"
  if grep -Eq '"kind"[[:space:]]*:' <<< "${networks}"; then
    echo "${service} is already connected to the kind Docker network."
  else
    docker network connect kind "${container_id}"
    echo "Connected ${service} to the kind Docker network."
  fi
done
