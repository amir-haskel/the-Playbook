#!/usr/bin/env bash
# Deploy a service version to an environment.
#
# DEMO: the cluster calls are simulated so the action is safe to run anywhere.
# Swap the `run` lines for real `helm upgrade` / `oc rollout status` calls.
#
# Parameters (in order): service, version, environment, dry_run
set -euo pipefail

service="${1:?service is required}"
version="${2:?version is required}"
environment="${3:-staging}"
dry_run="${4:-false}"
release="${service}-${environment}"

step() { printf '\n==> %s\n' "$*"; sleep 0.6; }
run()  { printf '$ %s\n' "$*"; sleep 0.4; }

echo "Deploying ${service}@${version} to ${environment} (dry-run: ${dry_run})"

step "Resolving image"
run "skopeo inspect docker://registry.example.com/${service}:${version}"
echo "digest: sha256:$(printf '%s' "${service}${version}" | sha256sum | cut -c1-64)"

step "Rendering Helm release ${release}"
helm_args="--namespace ${environment} --set image.tag=${version} --atomic --timeout 5m"
if [[ "${dry_run}" == "true" ]]; then
  run "helm upgrade --install ${release} charts/${service} ${helm_args} --dry-run=server"
  echo "dry-run complete — no changes applied."
  exit 0
fi
run "helm upgrade --install ${release} charts/${service} ${helm_args}"
echo "Release \"${release}\" has been upgraded. Happy Helming!"

step "Waiting for rollout"
for i in 1 2 3; do
  echo "Waiting for deployment \"${service}\" rollout to finish: ${i} of 3 updated replicas are available..."
  sleep 0.7
done
echo "deployment \"${service}\" successfully rolled out"

step "Recording deployment"
cat > "${OUTPUTS_DIR}/deploy-summary.json" <<JSON
{
  "service": "${service}",
  "version": "${version}",
  "environment": "${environment}",
  "release": "${release}",
  "deployed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "execution_id": "${PLAYBOOK_EXECUTION_ID:-local}"
}
JSON
echo "wrote deploy-summary.json"
