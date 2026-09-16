# Installation

- **Base SceneScape:** approximately 30-45 minutes
- **Modern UI + Keycloak:** allow an additional 10-20 minutes for the first image build and identity setup

This guide covers both the SceneScape 2026.2.0 services and the React/Keycloak modernization available on the `feature/react-keycloak-modern-ui` branch.

> **Migration model:** the React application is the modern operator console. The existing Django UI remains available as a fallback under `/legacy/`, and existing `/api/v1/*` token clients are intentionally preserved. Keycloak Bearer authentication is used by the modern browser-facing `/api/v2/*` endpoints.

## Prerequisites

- Verify you meet the [System Requirements](./system-requirements.md).
- Install Docker and Docker Compose as described in the system requirements.
- For the modern UI image build, the host must be able to download the Node/npm dependencies referenced by `modern-ui/package.json`.
- For Kubernetes deployment, install Helm and `kubectl` and make the modern UI image available to the cluster.

## Step 1: Get SceneScape

### Modernized feature branch

Clone this fork when you want the React/Keycloak implementation documented below:

```bash
git clone https://github.com/guruzen/scenescape.git
cd scenescape
git checkout feature/react-keycloak-modern-ui
```

The branch is based on SceneScape `2026.2.0` and keeps the upstream service architecture intact while adding the modern browser experience.

### Upstream release only

If you only need the original SceneScape release without the modernization, download a release from <https://github.com/open-edge-platform/scenescape/releases> or clone the upstream repository and select the appropriate release/tag.

> The React UI, Keycloak bridge, `/api/v2` browser API and the configuration in this section are specific to the modernization branch and are not present in the unmodified upstream `2026.2.0` release.

## Step 2: Build the SceneScape container images

Build the normal SceneScape images:

```bash
make
```

The build may take around 15 minutes depending on the target machine. By default, builds run in parallel using the available processors. To build sequentially:

```bash
make JOBS=1
```

The modern UI is built by Docker when the Compose overlay is started. You can also build it explicitly:

```bash
docker build -t intel/scenescape-modern-ui:$(cat version.txt) modern-ui
```

### Optional: list image dependencies

```bash
make list-dependencies
```

## Step 3: Deploy the base SceneScape demo

Set the Django superuser password. This remains useful for the legacy UI and is separate from Keycloak credentials.

```bash
export SUPASS='<choose-a-strong-django-admin-password>'
make demo
```

The Docker Compose demo targets are tiered:

| Target | Includes |
| --- | --- |
| `demo` | Core services with tracking, without ReID |
| `demo-reid` | `demo` plus the ReID vector database |
| `demo-all` | `demo-reid` plus cluster analytics and mapping services |

The ReID targets use VDMS by default. Set `REID_BACKEND=qdrant` to use Qdrant:

```bash
make demo-reid
make demo-reid REID_BACKEND=qdrant
```

`make demo` generates the root `docker-compose.yml` from the release Compose definition. The modern UI is intentionally supplied as an overlay so the original deployment remains usable on its own.

## Step 4: Enable the modern UI and Keycloak with Docker Compose

The branch contains `sample_data/docker-compose.modern-ui-override.yml`. It adds:

- Keycloak 26.7.3 with the SceneScape realm imported from `modern-ui/keycloak/scenescape-realm.json`;
- the React/Tailwind UI and Nginx gateway on port `8088`;
- Keycloak/JWKS configuration in the Django manager for `/api/v2`;
- same-origin `/auth`, `/api` and `/legacy` proxying through the modern UI;
- persistent local Keycloak data in a named volume.

### 4.1 Set the Keycloak bootstrap administrator password

```bash
export KEYCLOAK_ADMIN_USERNAME=admin
export KEYCLOAK_ADMIN_PASSWORD='<choose-a-strong-keycloak-admin-password>'
```

Do not reuse `SUPASS`. The Keycloak bootstrap administrator manages the identity server; it is not an everyday SceneScape operator account.

### 4.2 Start/reconcile the stack with the modernization overlay

For the normal controller demo:

```bash
docker compose \
  -f docker-compose.yml \
  -f sample_data/docker-compose.modern-ui-override.yml \
  --profile controller \
  up -d --build
```

The command reuses the base SceneScape services, recreates the manager with the OIDC environment, and adds `keycloak` and `modern-ui`.

Check the services:

```bash
docker compose \
  -f docker-compose.yml \
  -f sample_data/docker-compose.modern-ui-override.yml \
  --profile controller \
  ps
```

For local evaluation, use:

- Modern operations UI: <http://localhost:8088>
- Keycloak admin console: <http://localhost:8088/auth/admin/>
- Django fallback through the modern gateway: <http://localhost:8088/legacy/>
- Original Django endpoint: <https://localhost>

The imported development realm is intentionally configured for `localhost:8088` and `127.0.0.1:8088`.

### 4.3 Create the first SceneScape user

1. Open <http://localhost:8088/auth/admin/>.
2. Sign in with `KEYCLOAK_ADMIN_USERNAME` and `KEYCLOAK_ADMIN_PASSWORD`.
3. Select the **scenescape** realm. Do not create application users in the Keycloak master realm.
4. Open **Users** and create a user with a username and, preferably, email/name attributes.
5. Under **Credentials**, set a password for the user. Disable the temporary-password requirement if this is an evaluation account that should sign in immediately.
6. Under **Role mapping**, assign one of the SceneScape realm roles:

| Realm role | Intended use |
| --- | --- |
| `scenescape-viewer` | Normal operator/read access |
| `scenescape-admin` | Administrative operations exposed by the modern API |

The Django OIDC bridge auto-provisions an active Django user on the first authenticated `/api/v2` request by default. A `scenescape-admin` role produces request-scoped Django admin/superuser flags; that elevation is not persisted into the Django user record.

### 4.4 Sign in to the modern UI

Browse to <http://localhost:8088>. The browser is redirected to Keycloak using the OpenID Connect Authorization Code flow with PKCE S256. After authentication, the UI calls the manager through `/api/v2/*` using a Bearer access token.

The original machine/API behavior is unchanged:

- `/api/v1/*` continues to use the existing SceneScape/DRF token model;
- `/api/v2/*` is the modern browser API and accepts Keycloak Bearer access tokens;
- Django remains available under `/legacy/` during the migration.

## Step 5: Understand the Keycloak configuration

The development realm file is `modern-ui/keycloak/scenescape-realm.json`.

It creates:

- realm: `scenescape`;
- public OIDC client: `scenescape-ui`;
- Standard Authorization Code flow: enabled;
- PKCE challenge method: `S256`;
- Direct Access Grants/password grant: disabled;
- implicit flow: disabled;
- roles: `scenescape-viewer` and `scenescape-admin`.

### Browser/runtime variables

The modern UI creates `config.js` at container startup from these variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SCENESCAPE_API_BASE_URL` | empty/same origin | Base URL used by browser API calls |
| `SCENESCAPE_KEYCLOAK_URL` | `/auth` | Browser-visible Keycloak base URL |
| `SCENESCAPE_KEYCLOAK_REALM` | `scenescape` | OIDC realm |
| `SCENESCAPE_KEYCLOAK_CLIENT_ID` | `scenescape-ui` | Public browser client |
| `SCENESCAPE_LEGACY_BASE_URL` | `/legacy/` | Django fallback route |
| `SCENESCAPE_APP_TITLE` | `SceneScape` | UI title |
| `SCENESCAPE_API_UPSTREAM` | deployment-specific | Nginx upstream for Django/API/media/static |
| `SCENESCAPE_KEYCLOAK_UPSTREAM` | deployment-specific | Nginx upstream used for `/auth/` when Keycloak is proxied locally |

### Django/manager OIDC variables

The `/api/v2` authentication bridge reads these variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `KEYCLOAK_ENABLED` | `true` | Enables Bearer-token processing for the modern API |
| `KEYCLOAK_ISSUER_URL` | derived | Expected token `iss`; when set, it must match the access token exactly |
| `KEYCLOAK_JWKS_URL` | issuer + certs path | URL used by the manager to retrieve signing keys |
| `KEYCLOAK_URL` | `http://keycloak:8080/auth` | Keycloak base URL used when the issuer is derived |
| `KEYCLOAK_REALM` | `scenescape` | Realm name |
| `KEYCLOAK_CLIENT_ID` | `scenescape-ui` | Client whose roles can also be read from `resource_access` |
| `KEYCLOAK_ADMIN_ROLE` | `scenescape-admin` | Role mapped to request-scoped admin privileges |
| `KEYCLOAK_AUTO_PROVISION_USERS` | `true` | Creates a Django user at first successful OIDC request |
| `KEYCLOAK_VERIFY_SSL` | `true` | TLS verification for JWKS retrieval |
| `KEYCLOAK_API_AUDIENCE` | empty | Optional audience check; when empty, `aud` is not required |

### Public issuer versus private JWKS URL

These URLs are deliberately separate. A browser may receive a token whose issuer is public:

```text
https://scenescape.example.com/auth/realms/scenescape
```

while the Django manager can fetch keys using a cluster-private route:

```text
http://keycloak:8080/auth/realms/scenescape/protocol/openid-connect/certs
```

`KEYCLOAK_ISSUER_URL` must match the token's `iss` claim. `KEYCLOAK_JWKS_URL` only needs to be reachable by the manager and serve the signing keys for that issuer. This split avoids forcing backend containers to resolve the public ingress hostname.

## Step 6: Configure a non-local URL

The bundled realm JSON contains localhost redirect URIs so that a checked-in development realm does not contain an unsafe wildcard for arbitrary hosts.

For a remote evaluation deployment:

1. Set the exact external origin before starting the Compose overlay, for example:

   ```bash
   export SCENESCAPE_PUBLIC_URL=https://scenescape.example.com
   ```

2. Terminate TLS in a reverse proxy/load balancer in front of the modern UI gateway.
3. In Keycloak, edit **Clients > scenescape-ui** and set:
   - Valid redirect URIs: `https://scenescape.example.com/*`
   - Web origins: `https://scenescape.example.com`
   - Valid post-logout redirect URI: `https://scenescape.example.com/*`
4. Restart/recreate the `web`, `keycloak` and `modern-ui` services if the public URL/issuer changed.

Avoid broad production redirect patterns such as `*` origins.

## Step 7: Kubernetes / Helm

The chart contains explicit `modernUI` and `keycloak` values. The modern UI remains disabled by default so an unmodified 2026.2.0 deployment does not suddenly depend on a new image.

### 7.1 Build and publish the modern UI image

The cluster must be able to pull the image:

```bash
docker build -t registry.example.com/scenescape-modern-ui:2026.2.0-modern.1 modern-ui
docker push registry.example.com/scenescape-modern-ui:2026.2.0-modern.1
```

### 7.2 Embedded Keycloak for lab/evaluation

Add these values to the normal SceneScape Helm values used by your deployment:

```yaml
certdomain: scenescape.example.com

modernUI:
  enabled: true
  image:
    repository: registry.example.com/scenescape-modern-ui
    tag: 2026.2.0-modern.1
  auth:
    realm: scenescape
    clientId: scenescape-ui

keycloak:
  enabled: true
  bootstrapAdminUsername: admin
  # Prefer an existing Secret or allow the chart to generate the password.
  bootstrapAdminPassword: ""
```

When `modernUI.enabled=true`, ingress routes `/` to the modern Nginx gateway. The gateway proxies `/api`, `/legacy` and `/auth` to the appropriate services. The Django manager receives the corresponding public issuer and cluster-private JWKS settings.

If the chart generated the Keycloak bootstrap password, retrieve it using the actual Helm release name and namespace. For a release named `scenescape` in namespace `scenescape`:

```bash
kubectl -n scenescape get secret scenescape-keycloak-bootstrap \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

> **Important:** the embedded chart uses Keycloak `start-dev`. It is provided for evaluation/lab deployments, not as a recommended production identity topology.

### 7.3 External/managed Keycloak for production-style deployments

Create/import the `scenescape` realm and configure a public client equivalent to `modern-ui/keycloak/scenescape-realm.json`. Use the exact production SceneScape origin for redirect URIs and web origins.

Example chart values:

```yaml
certdomain: scenescape.example.com

modernUI:
  enabled: true
  image:
    repository: registry.example.com/scenescape-modern-ui
    tag: 2026.2.0-modern.1
  auth:
    realm: scenescape
    clientId: scenescape-ui
    keycloakUrl: https://id.example.com/auth
    issuerUrl: https://id.example.com/auth/realms/scenescape
    # Optional when the manager should use a different/private route:
    jwksUrl: https://id.example.com/auth/realms/scenescape/protocol/openid-connect/certs
    verifySsl: true
    autoProvisionUsers: true
    adminRole: scenescape-admin

keycloak:
  enabled: false
```

For production, use TLS with a trusted certificate, persistent Keycloak storage/database, backups, restricted administration, secret rotation and your organization's identity lifecycle/MFA policies.

## Step 8: Verify the deployment

### Base SceneScape

```bash
curl -k https://localhost/api/v1/health
```

The original Django interface should still be reachable at <https://localhost> for a local Compose deployment.

### Modern gateway

```bash
curl -fsS http://localhost:8088/healthz
```

Expected response:

```text
ok
```

Then verify in the browser:

1. Open <http://localhost:8088>.
2. Confirm redirect to the `scenescape` Keycloak realm.
3. Sign in with the application user created earlier, not the Keycloak bootstrap administrator.
4. Confirm **Shift overview** loads and `/api/v2/overview` returns HTTP 200 in browser developer tools.
5. Open **Django fallback** and confirm the legacy application remains reachable under `/legacy/`.
6. If the account has `scenescape-admin`, confirm the UI identifies it as an administrator.

Useful logs:

```bash
docker compose \
  -f docker-compose.yml \
  -f sample_data/docker-compose.modern-ui-override.yml \
  --profile controller \
  logs --tail=200 web keycloak modern-ui
```

## Keycloak troubleshooting

| Symptom | What to check |
| --- | --- |
| `Invalid parameter: redirect_uri` | The `scenescape-ui` client does not contain the exact browser origin/path in Valid Redirect URIs. |
| Login succeeds but `/api/v2/*` returns 401 | Compare the token `iss` with `KEYCLOAK_ISSUER_URL`; they must match exactly, including scheme, hostname, port and `/auth` path. |
| Manager cannot retrieve signing keys | Verify `KEYCLOAK_JWKS_URL` is reachable from the manager container/pod. For embedded deployments, prefer the internal service URL. |
| TLS/JWKS certificate error | Install the correct CA/trust chain. `KEYCLOAK_VERIFY_SSL=false` should only be a temporary lab diagnostic, not the production fix. |
| User authenticates but cannot perform admin actions | Assign the `scenescape-admin` realm role and sign in again so a new access token contains the role. |
| Browser continuously redirects to login | Check browser-visible `SCENESCAPE_KEYCLOAK_URL`, Keycloak hostname/proxy settings, cookies and redirect URIs. |
| Modern UI loads but API calls fail | Check `SCENESCAPE_API_UPSTREAM`, manager health, Nginx logs and `/api/v2` authentication. |
| `/api/v1` client stopped working after migration | The modernization is not intended to change `/api/v1`. Verify the client still sends the existing `Token` authorization scheme rather than Bearer. |

## Docker Compose profiles

SceneScape uses [Docker Compose profiles](https://docs.docker.com/compose/how-tos/profiles/) to organize services into logical groups.

| Profile | Description |
| --- | --- |
| `controller` | Scene Controller (tracking) + Analytics service. Used by `make demo`. |
| `mapping` | Enables the mapping service. |
| `cluster-analytics` | Enables cluster analytics. |
| `tracker` | Tracker + Analytics services without Scene Controller. |

For example:

```bash
docker compose --profile controller up -d
```

When the modern overlay is in use, keep the same two `-f` arguments for subsequent Compose operations so Docker Compose sees `keycloak` and `modern-ui` as part of the project.

## Stopping the system

With the modern overlay:

```bash
docker compose \
  -f docker-compose.yml \
  -f sample_data/docker-compose.modern-ui-override.yml \
  --profile controller \
  down --remove-orphans
```

This leaves named volumes intact. Adding `-v` deletes SceneScape data volumes **and the local Keycloak database**, including users and role assignments.

For the original stack without the overlay:

```bash
docker compose --profile controller down --remove-orphans
```

## Security notes

- Do not use the Keycloak bootstrap administrator as a normal SceneScape user.
- Do not commit passwords, client secrets or access tokens.
- The browser client is intentionally public; PKCE S256 protects the authorization-code flow. Do not add a client secret to frontend JavaScript.
- Keep Direct Access Grants disabled unless there is a separate, explicitly reviewed non-browser requirement.
- Prefer a managed/external Keycloak for production deployments.
- Use a trusted TLS certificate and keep `KEYCLOAK_VERIFY_SSL=true`.
- Keep `/api/v1` compatibility credentials separate from browser identity.
- Treat the included self-signed SceneScape certificates and embedded Keycloak `start-dev` setup as evaluation conveniences, not a complete production security configuration.

## Optional: LiDAR-Intersection fusion demo

A separate opt-in demo fuses a recorded LiDAR point-cloud stream with a recorded camera image sequence. Run it with `make demo-lidar` and see [Run the LiDAR-Intersection Fusion Demo](../how-to-guides/run-lidar-intersection-demo.md).

## Summary

After the modernization steps, a local installation has two browser experiences backed by the same SceneScape domain services:

- the React/Tailwind operations console at `http://localhost:8088`, authenticated through Keycloak;
- the existing Django application retained as the migration fallback.

The modern UI currently covers the modern shell, identity, `/api/v2` resource access and operations/control-plane navigation. Historical replay, durable incident workflow and long-term trend storage require additional backend services; the UI intentionally does not fabricate those capabilities when the services are absent.

## Next steps

- Review the [SceneScape user guide overview](../index.md).
- Review the [modern operations UX direction](../../ux/operations-v2/README.md).
- See [Deploy SceneScape](../how-to-guides/deploy-scenescape-using-prebuilt-containers.md) for the original prebuilt-container deployment flow.
- See [Hardening Guide for Custom TLS](../additional-resources/hardening-guide.md) before exposing a deployment outside a lab environment.
- See [Release Notes](../release-notes.md).
