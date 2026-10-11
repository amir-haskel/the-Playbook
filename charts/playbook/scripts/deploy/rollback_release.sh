#!/usr/bin/env bash
# Roll a Helm release back to its previous revision.
#
# DEMO: simulated. Replace `run` with the real commands for your cluster.
#
# Parameters (in order): service, environment, reason
set -euo pipefail

service="${1:?service is required}"
environment="${2:?environment is required}"
reason="${3:-not specified}"
release="${service}-${environment}"

run() { printf '$ %s\n' "$*"; sleep 0.5; }

echo "Rolling back ${release} — reason: ${reason}"
run "helm history ${release} --namespace ${environment} --max 3"
printf 'REVISION\tSTATUS    \tCHART             \tDESCRIPTION\n'
printf '41      \tsuperseded\t%s-2.3.0  \tUpgrade complete\n' "${service}"
printf '42      \tdeployed  \t%s-2.4.0  \tUpgrade complete\n' "${service}"
run "helm rollback ${release} 41 --namespace ${environment} --wait"
echo "Rollback was a success! Happy Helming!"
