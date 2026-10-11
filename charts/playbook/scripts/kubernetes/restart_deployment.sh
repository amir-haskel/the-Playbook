#!/usr/bin/env bash
# Rolling-restart a Deployment (e.g. to pick up a rotated Secret).
#
# DEMO: simulated `oc` output.
#
# Parameters (in order): namespace, deployment
set -euo pipefail

namespace="${1:?namespace is required}"
deployment="${2:?deployment is required}"

printf '$ oc rollout restart deployment/%s -n %s\n' "${deployment}" "${namespace}"
sleep 0.5
echo "deployment.apps/${deployment} restarted"
printf '$ oc rollout status deployment/%s -n %s --timeout=5m\n' "${deployment}" "${namespace}"
for i in 1 2 3; do
  sleep 0.6
  echo "Waiting for deployment \"${deployment}\" rollout to finish: ${i} out of 3 new replicas have been updated..."
done
echo "deployment \"${deployment}\" successfully rolled out"
