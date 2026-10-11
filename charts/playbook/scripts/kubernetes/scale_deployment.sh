#!/usr/bin/env bash
# Scale a Deployment to a given replica count.
#
# DEMO: simulated `oc` output.
#
# Parameters (in order): namespace, deployment, replicas
set -euo pipefail

namespace="${1:?namespace is required}"
deployment="${2:?deployment is required}"
replicas="${3:?replicas is required}"

if ! [[ "${replicas}" =~ ^[0-9]+$ ]] || (( replicas > 20 )); then
  echo "replicas must be an integer between 0 and 20" >&2
  exit 2
fi

printf '$ oc scale deployment/%s -n %s --replicas=%s\n' "${deployment}" "${namespace}" "${replicas}"
sleep 0.5
echo "deployment.apps/${deployment} scaled"
printf '$ oc get deployment/%s -n %s\n' "${deployment}" "${namespace}"
printf 'NAME\tREADY\tUP-TO-DATE\tAVAILABLE\n%s\t%s/%s\t%s\t%s\n' \
  "${deployment}" "${replicas}" "${replicas}" "${replicas}" "${replicas}"
