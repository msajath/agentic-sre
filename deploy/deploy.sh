#!/usr/bin/env bash
set -euo pipefail

deploy_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
env_file="${SRE_ENV_FILE:-$deploy_dir/.env}"

if [[ ! -f "$env_file" ]]; then
  printf 'Missing deployment environment file: %s\n' "$env_file" >&2
  exit 1
fi
permissions="$(stat -c %a "$env_file")"
if (( (8#$permissions & 8#077) != 0 )); then
  printf 'Restrict deployment environment file permissions: chmod 600 %s\n' "$env_file" >&2
  exit 1
fi

compose=(docker compose --project-name agentic-sre --env-file "$env_file" -f "$deploy_dir/compose.vps.yml")
"${compose[@]}" config --quiet
"${compose[@]}" pull

postgres_container="$("${compose[@]}" ps -q postgres)"
if [[ -n "$postgres_container" && "$(docker inspect -f '{{.State.Running}}' "$postgres_container")" == true ]]; then
  bash "$deploy_dir/backup.sh"
fi

"${compose[@]}" up -d --no-build --pull never

host_port="$("${compose[@]}" port agentic-sre 8000 | tail -n 1)"
host_port="${host_port##*:}"
base_url="http://127.0.0.1:$host_port"
for attempt in {1..90}; do
  if curl --fail --silent --max-time 3 "$base_url/readyz" > /dev/null; then
    curl --fail --silent --max-time 3 "$base_url/login" | grep -qi '<html'
    curl --fail --silent --max-time 3 "$base_url/signup" | grep -qi '<html'
    printf 'Deployment ready on %s\n' "$base_url"
    exit 0
  fi
  sleep 1
done

"${compose[@]}" ps >&2
"${compose[@]}" logs --tail=100 agentic-sre migrate postgres >&2
printf 'Deployment did not become ready within 90 seconds.\n' >&2
exit 1
