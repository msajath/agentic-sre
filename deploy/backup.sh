#!/usr/bin/env bash
set -euo pipefail

deploy_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
env_file="${SRE_ENV_FILE:-$deploy_dir/.env}"
backup_dir="${SRE_BACKUP_DIR:-$deploy_dir/backups}"

if [[ ! -f "$env_file" ]]; then
  printf 'Missing deployment environment file: %s\n' "$env_file" >&2
  exit 1
fi
permissions="$(stat -c %a "$env_file")"
if (( (8#$permissions & 8#077) != 0 )); then
  printf 'Restrict deployment environment file permissions: chmod 600 %s\n' "$env_file" >&2
  exit 1
fi

umask 077
mkdir -p -- "$backup_dir"
compose=(docker compose --project-name agentic-sre --env-file "$env_file" -f "$deploy_dir/compose.vps.yml")
"${compose[@]}" config --quiet

temporary="$(mktemp "$backup_dir/.agentic-sre-backup.XXXXXXXX")"
trap 'rm -f -- "$temporary"' EXIT
"${compose[@]}" exec -T postgres pg_dump -U agentic_sre -d agentic_sre --format=custom > "$temporary"
"${compose[@]}" exec -T postgres pg_restore --list < "$temporary" > /dev/null

backup="$backup_dir/agentic-sre-$(date -u +%Y%m%dT%H%M%SZ)-${temporary##*.}.dump"
mv -- "$temporary" "$backup"
trap - EXIT
printf 'Backup verified: %s\n' "$backup"
