# SPDX-License-Identifier: Apache-2.0
"""Keycloak/OIDC authentication bridge for the SceneScape modern API.

Browser Bearer tokens are validated against Keycloak. Existing DRF Token
clients remain supported by HybridAuthentication and the legacy v1 API is not
modified by this module.
"""

from __future__ import annotations

import os
import ssl
from functools import lru_cache
from typing import Any

import jwt
from jwt.exceptions import PyJWKClientError, PyJWTError
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool) -> bool:
  value = os.environ.get(name)
  if value is None:
    return default
  return value.strip().lower() in TRUE_VALUES


def keycloak_enabled() -> bool:
  return _env_bool("KEYCLOAK_ENABLED", True)


def _issuer() -> str:
  explicit = os.environ.get("KEYCLOAK_ISSUER_URL", "").rstrip("/")
  if explicit:
    return explicit
  realm = os.environ.get("KEYCLOAK_REALM", "scenescape")
  base = os.environ.get("KEYCLOAK_URL", "http://keycloak:8080/auth").rstrip("/")
  return f"{base}/realms/{realm}"


def _jwks_url() -> str:
  explicit = os.environ.get("KEYCLOAK_JWKS_URL", "").strip()
  return explicit or f"{_issuer()}/protocol/openid-connect/certs"


def extract_roles(payload: dict[str, Any]) -> list[str]:
  roles: set[str] = set()
  realm_access = payload.get("realm_access")
  if isinstance(realm_access, dict):
    values = realm_access.get("roles", [])
    if isinstance(values, list):
      roles.update(str(value) for value in values)
  client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "scenescape-ui")
  resource_access = payload.get("resource_access")
  if isinstance(resource_access, dict):
    client_access = resource_access.get(client_id)
    if isinstance(client_access, dict):
      values = client_access.get("roles", [])
      if isinstance(values, list):
        roles.update(str(value) for value in values)
  return sorted(roles)


@lru_cache(maxsize=8)
def _jwk_client(jwks_url: str, verify_ssl: bool) -> jwt.PyJWKClient:
  context = None if verify_ssl else ssl._create_unverified_context()  # noqa: SLF001
  return jwt.PyJWKClient(
    jwks_url,
    cache_keys=True,
    cache_jwk_set=True,
    lifespan=300,
    timeout=10,
    ssl_context=context,
  )


class KeycloakJWTAuthentication(authentication.BaseAuthentication):
  keyword = "Bearer"

  def authenticate(self, request):
    if not keycloak_enabled():
      return None
    header = authentication.get_authorization_header(request).split()
    if not header:
      return None
    if header[0].decode(errors="ignore").lower() != self.keyword.lower():
      return None
    if len(header) != 2:
      raise exceptions.AuthenticationFailed("Malformed Bearer authorization header")
    try:
      raw_token = header[1].decode("utf-8")
      verify_ssl = _env_bool("KEYCLOAK_VERIFY_SSL", True)
      signing_key = _jwk_client(_jwks_url(), verify_ssl).get_signing_key_from_jwt(raw_token).key
      audience = os.environ.get("KEYCLOAK_API_AUDIENCE", "").strip()
      decode_kwargs: dict[str, Any] = {
        "algorithms": ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
        "issuer": _issuer(),
        "options": {"require": ["exp", "iat", "iss", "sub"], "verify_aud": bool(audience)},
      }
      if audience:
        decode_kwargs["audience"] = audience
      payload = jwt.decode(raw_token, signing_key, **decode_kwargs)
    except (UnicodeError, PyJWTError, PyJWKClientError, ValueError, OSError) as exc:
      raise exceptions.AuthenticationFailed(f"OIDC access token rejected: {exc}") from exc

    username = str(payload.get("preferred_username") or payload.get("sub") or "").strip()
    if not username:
      raise exceptions.AuthenticationFailed("OIDC token does not identify a user")

    User = get_user_model()
    user = User.objects.filter(username=username).first()
    if user is None:
      if not _env_bool("KEYCLOAK_AUTO_PROVISION_USERS", True):
        raise exceptions.AuthenticationFailed("OIDC user is not provisioned in SceneScape")
      user = User(username=username)
      user.set_unusable_password()

    if not user.is_active:
      raise exceptions.AuthenticationFailed("SceneScape user is disabled")

    changed = user.pk is None
    for field, claim in (("email", "email"), ("first_name", "given_name"), ("last_name", "family_name")):
      value = str(payload.get(claim) or "")
      if value and getattr(user, field, "") != value:
        setattr(user, field, value)
        changed = True
    if changed:
      user.save()

    roles = extract_roles(payload)
    if os.environ.get("KEYCLOAK_ADMIN_ROLE", "scenescape-admin") in roles:
      # Request-scoped elevation only; these flags are not persisted.
      user.is_staff = True
      user.is_superuser = True

    request.keycloak_claims = payload
    request.keycloak_roles = roles
    return user, payload

  def authenticate_header(self, request):
    return 'Bearer realm="scenescape"'


class HybridAuthentication(authentication.BaseAuthentication):
  """Bearer -> Keycloak; Token -> existing DRF token authentication."""

  def __init__(self):
    self.keycloak = KeycloakJWTAuthentication()
    self.legacy_token = authentication.TokenAuthentication()

  def authenticate(self, request):
    header = authentication.get_authorization_header(request).split()
    if not header:
      return None
    scheme = header[0].decode(errors="ignore").lower()
    if scheme == "bearer":
      return self.keycloak.authenticate(request)
    if scheme == "token":
      return self.legacy_token.authenticate(request)
    return None

  def authenticate_header(self, request):
    return self.keycloak.authenticate_header(request)
