{{- define "native.name" -}}
{{- printf "%s-native" .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}
{{- define "native.dbEnv" -}}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ required "runtimeSecret must name a Secret containing DATABASE_URL and API_SIGNING_KEY" .Values.runtimeSecret }}
      key: DATABASE_URL
{{- end -}}
{{- define "native.security" -}}
runAsNonRoot: true
runAsUser: 1000
runAsGroup: 1000
allowPrivilegeEscalation: false
capabilities:
  drop: [ALL]
seccompProfile:
  type: RuntimeDefault
{{- end -}}
{{- define "native.authVolumes" -}}
- name: service-auth
  secret:
    secretName: {{ required "serviceAuthSecret is required" .Values.serviceAuthSecret }}
- name: api-tls
  secret:
    secretName: {{ required "tls.existingSecret is required" .Values.tls.existingSecret }}
{{- end -}}
