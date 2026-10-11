# playbook Helm chart

Deploys **the Playbook** self-service portal to Kubernetes or OpenShift. The
scripts behind the portal's buttons are part of the chart: everything in
[`scripts/`](scripts/) is rendered into one ConfigMap and mounted read-only at
`/scripts`, where the app discovers them.

```bash
helm upgrade --install playbook ./charts/playbook -n playbook --create-namespace
# OpenShift: also expose it with a Route
helm upgrade --install playbook ./charts/playbook -n playbook --set route.enabled=true
```

## How scripts reach the pod

```
charts/playbook/scripts/            ConfigMap <release>-scripts          Pod
├── deploy/deploy_service.sh   ──►  deploy__deploy_service.sh    ──►    /scripts/deploy/deploy_service.sh
├── database/backup_database.py──►  database__backup_database.py ──►    /scripts/database/backup_database.py
└── ...                             (one key per file)                  (volume items restore sub-folders)
```

* `templates/_helpers.tpl` (`playbook.scripts`) collects `.Files.Glob "scripts/**"` plus
  `scripts.inline` from values, flattens each path into a valid ConfigMap key
  (`/` → `__`) and fails the render on invalid names, key collisions, or when
  the total would exceed the 1 MiB ConfigMap limit.
* The Deployment's `configMap` volume uses `items` to map each key back to its
  original relative path, so the folder structure you see in the repo is the one
  admins see in the script picker.
* CRLF line endings are normalised to LF at render time, so a chart packaged on
  Windows still produces runnable bash scripts.
* Files are mounted `0555` (read + execute, never writable) on a read-only volume.
* **Updating scripts:** editing a script's content is hot-reloaded by the kubelet
  (about a minute) with no pod restart, so running executions are not interrupted.
  Adding or removing a file in a nested folder changes the volume `items` and rolls
  the pod. Set `scripts.restartOnChange=true` to always roll on any change.

> Why `scripts/` sits at the chart root and not under `templates/`: Helm renders
> every file in `templates/` as a manifest and does not let `.Files` read from it.
> A sibling folder is the supported place for files that templates embed.

### Adding scripts without forking the chart

```yaml
# my-values.yaml
scripts:
  inline:
    ops/flush_cache.sh: |
      #!/usr/bin/env bash
      redis-cli -h "$REDIS_HOST" FLUSHALL
```

or bring your own ConfigMap (flat layout) with `scripts.existingConfigMap`.

## Design decisions

| Concern | What the chart does |
|---|---|
| **State** | SQLite on its own PVC (`persistence.db`), execution outputs and uploads on a second PVC (`persistence.store`) so each can be sized and backed up independently. Both PVCs carry `helm.sh/resource-policy: keep` so `helm uninstall` never deletes history. |
| **Single writer** | `replicas: 1` + `strategy: Recreate` are fixed in the template, not values: two pods must never open the same SQLite file. There is deliberately no HPA or PDB. |
| **Secrets** | Admin password and session key are generated on first install and re-read with `lookup` on upgrade, so they stay stable. `auth.existingSecret` hands ownership to External Secrets / Sealed Secrets / Vault. A `checksum/secret` annotation rolls the pod when a chart-managed secret changes. |
| **Pod security** | Passes the `restricted` Pod Security Standard: non-root, `readOnlyRootFilesystem`, all capabilities dropped, no privilege escalation, `RuntimeDefault` seccomp. A writable `emptyDir` is mounted at `/tmp` (also `HOME`). |
| **OpenShift** | `openshift.adaptSecurityContext=auto` detects OpenShift through the API and drops fixed `runAsUser`/`fsGroup`, so the `restricted-v2` SCC can assign the namespace UID. The image is group-0 writable for arbitrary UIDs. Optional `Route` with a 1h HAProxy timeout for long log streams. |
| **Least privilege** | Dedicated ServiceAccount with token automount **off**; `enableServiceLinks: false` keeps other services' variables out of the scripts' environment; optional NetworkPolicy. |
| **Streaming** | Route/Ingress defaults keep Server-Sent Events open and unbuffered (`haproxy.router.openshift.io/timeout`, `proxy-buffering: off`). |
| **Health** | Separate startup, readiness and liveness probes on `/healthz`; `helm test` checks the Service using the app image itself (works air-gapped). |
| **Guard rails** | `values.schema.json` validates values before rendering (enums, path formats, sizes, digest format). |

## Values

| Key | Default | Description |
|---|---|---|
| `image.repository` | `playbook` | Container image repository (set to your registry) |
| `image.tag` | `""` (→ `appVersion`) | Image tag |
| `image.digest` | `""` | Pin by digest (wins over tag) |
| `branding.article` / `branding.name` | `the` / `Playbook` | Header wordmark |
| `auth.adminPassword` | `""` (generated) | Admin password for `/admin` |
| `auth.sessionSecret` | `""` (generated) | Session-cookie signing key |
| `auth.existingSecret` | `""` | Use your own Secret (`ADMIN_PASSWORD`, `SESSION_SECRET`, optional tokens) |
| `integrations.gitlab.url` / `.token` | `""` | GitLab API for dynamic dropdowns |
| `integrations.openshift.url` / `.token` | `""` | OpenShift/Kubernetes API for dynamic dropdowns |
| `scripts.enabled` | `true` | Ship scripts via ConfigMap |
| `scripts.mountPath` | `/scripts` | Mount path (`SCRIPTS_DIR`) |
| `scripts.glob` | `scripts/**` | Which chart files to ship |
| `scripts.inline` | `{}` | Extra scripts from values |
| `scripts.defaultMode` | `0555` | File mode of mounted scripts |
| `scripts.existingConfigMap` | `""` | Mount an existing ConfigMap instead |
| `scripts.restartOnChange` | `false` | Roll the pod on any script change |
| `persistence.db.*` | `256Mi`, RWO, `retain: true` | SQLite volume (`enabled`, `size`, `storageClass`, `existingClaim`, `accessModes`, `annotations`) |
| `persistence.store.*` | `5Gi`, RWO, `retain: true` | Outputs + uploads volume (same keys) |
| `extraEnv` / `extraEnvFrom` | `[]` | Extra environment for the app and its scripts |
| `extraVolumes` / `extraVolumeMounts` | `[]` | e.g. a kubeconfig or CA bundle for scripts |
| `serviceAccount.create` / `.automount` | `true` / `false` | ServiceAccount and token mount |
| `openshift.adaptSecurityContext` | `auto` | `auto`, `force` or `disabled` |
| `podSecurityContext` / `securityContext` | restricted PSS | Security contexts |
| `service.type` / `.port` | `ClusterIP` / `8000` | Service |
| `route.enabled` | `false` | OpenShift Route (`host`, `annotations`, `tls.*`) |
| `ingress.enabled` | `false` | Kubernetes Ingress (`className`, `annotations`, `hosts`, `tls`) |
| `resources` | 100m / 128Mi req, 512Mi limit | No CPU limit by default |
| `probes.startup` / `.readiness` / `.liveness` | `/healthz` | Probe specs |
| `terminationGracePeriodSeconds` | `30` | Time for script cleanup traps on shutdown |
| `networkPolicy.enabled` | `false` | Restrict ingress to the HTTP port (`ingressFrom`, `egress`) |
| `nodeSelector` / `tolerations` / `affinity` / `priorityClassName` | empty | Scheduling |

## Testing the chart

```bash
helm lint charts/playbook --strict
helm template pb charts/playbook | kubeconform -strict -summary
helm test playbook -n playbook
```
