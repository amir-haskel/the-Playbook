{{/*
Chart name, truncated to the 63-char DNS label limit.
*/}}
{{- define "playbook.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully-qualified app name. If the release name already contains the chart name
it is used as-is, so `helm install playbook ./charts/playbook` yields "playbook".
*/}}
{{- define "playbook.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "playbook.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels (Kubernetes recommended labels).
*/}}
{{- define "playbook.labels" -}}
helm.sh/chart: {{ include "playbook.chart" . }}
{{ include "playbook.selectorLabels" . }}
app.kubernetes.io/version: {{ .Values.image.tag | default .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: playbook
{{- end }}

{{/*
Selector labels — must stay immutable across upgrades.
*/}}
{{- define "playbook.selectorLabels" -}}
app.kubernetes.io/name: {{ include "playbook.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "playbook.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "playbook.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image reference: a digest pins the image immutably and wins over the tag.
*/}}
{{- define "playbook.image" -}}
{{- if .Values.image.digest }}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest }}
{{- else }}
{{- printf "%s:%s" .Values.image.repository (.Values.image.tag | default .Chart.AppVersion) }}
{{- end }}
{{- end }}

{{- define "playbook.secretName" -}}
{{- default (printf "%s-secrets" (include "playbook.fullname" .)) .Values.auth.existingSecret }}
{{- end }}

{{- define "playbook.scriptsConfigMapName" -}}
{{- default (printf "%s-scripts" (include "playbook.fullname" .)) .Values.scripts.existingConfigMap }}
{{- end }}

{{/*
True when the cluster is OpenShift (or the user forces OpenShift mode).
*/}}
{{- define "playbook.isOpenShift" -}}
{{- $mode := .Values.openshift.adaptSecurityContext | toString }}
{{- if eq $mode "force" }}true
{{- else if and (eq $mode "auto") (.Capabilities.APIVersions.Has "security.openshift.io/v1") }}true
{{- end }}
{{- end }}

{{/*
Pod security context. On OpenShift the restricted SCC assigns a UID/GID from
the namespace range, so fixed IDs are stripped to avoid admission failures.
*/}}
{{- define "playbook.podSecurityContext" -}}
{{- $ctx := deepCopy .Values.podSecurityContext }}
{{- if include "playbook.isOpenShift" . }}
{{- $ctx = omit $ctx "runAsUser" "runAsGroup" "fsGroup" }}
{{- end }}
{{- toYaml $ctx }}
{{- end }}

{{/*
Collect every script as a list of {key, path, content}.

ConfigMap keys may not contain "/", so a nested path such as
"deploy/rollout.sh" is stored under the key "deploy__rollout.sh" and mapped
back to its original relative path through the volume's `items`. This keeps
the operator's folder structure intact inside the pod.
*/}}
{{- define "playbook.scripts" -}}
{{- $scripts := list }}
{{- $prefix := .Values.scripts.glob | trimSuffix "**" | trimSuffix "*" }}
{{- range $path, $_ := .Files.Glob .Values.scripts.glob }}
{{- $rel := trimPrefix $prefix $path }}
{{- $base := base $rel }}
{{- if not (or (hasPrefix "." $base) (eq $base "README.md")) }}
{{- /* Normalise CRLF: a script checked out on Windows must still run under bash. */}}
{{- $scripts = append $scripts (dict "path" $rel "content" ($.Files.Get $path | replace "\r\n" "\n")) }}
{{- end }}
{{- end }}
{{- range $rel, $content := .Values.scripts.inline }}
{{- $scripts = append $scripts (dict "path" $rel "content" $content) }}
{{- end }}
{{- $seen := dict }}
{{- $total := 0 }}
{{- $out := list }}
{{- range $scripts }}
{{- $key := .path | replace "/" "__" }}
{{- if not (regexMatch "^[-._a-zA-Z0-9]+$" $key) }}
{{- fail (printf "script %q: names may only contain letters, digits, '-', '_' and '.'" .path) }}
{{- end }}
{{- if hasKey $seen $key }}
{{- fail (printf "script %q collides with another script (ConfigMap key %q)" .path $key) }}
{{- end }}
{{- $_ := set $seen $key true }}
{{- $total = add $total (len .content) }}
{{- $out = append $out (dict "key" $key "path" .path "content" .content) }}
{{- end }}
{{- if gt $total 1000000 }}
{{- fail (printf "scripts total %d bytes; a ConfigMap is limited to 1 MiB. Ship large tooling in the image instead." $total) }}
{{- end }}
{{- toJson (dict "items" $out) }}
{{- end }}
