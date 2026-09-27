# SPDX-License-Identifier: Apache-2.0
"""Keycloak-aware endpoints for the SceneScape modern operator console.

The v2 resource views intentionally reuse the existing v1 models, serializers
and validation logic. This keeps v1 machine-token compatibility intact while
allowing the browser console to use OIDC Bearer tokens.
"""

from __future__ import annotations

from django.apps import apps
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from manager import api as legacy_api
from manager.keycloak_auth import HybridAuthentication, extract_roles


def _count_model(*candidates: str):
  for name in candidates:
    try:
      model = apps.get_model("manager", name)
      if model is not None:
        return model.objects.count()
    except (LookupError, AttributeError):
      continue
  return None


def _roles(request) -> list[str]:
  if hasattr(request, "keycloak_roles"):
    return list(request.keycloak_roles)
  if isinstance(request.auth, dict):
    return extract_roles(request.auth)
  roles: list[str] = []
  if request.user.is_superuser or request.user.is_staff:
    roles.append("scenescape-admin")
  return roles


class ModernListThings(legacy_api.ListThings):
  authentication_classes = [HybridAuthentication]
  permission_classes = [IsAuthenticated]


class ModernManageThing(legacy_api.ManageThing):
  authentication_classes = [HybridAuthentication]
  permission_classes = [legacy_api.IsAdminOrReadOnly]


class SessionAPIView(APIView):
  authentication_classes = [HybridAuthentication]
  permission_classes = [IsAuthenticated]

  def get(self, request):
    roles = _roles(request)
    is_admin = bool(request.user.is_superuser or request.user.is_staff or "scenescape-admin" in roles)
    return Response({
      "authenticated": True,
      "username": request.user.get_username(),
      "display_name": request.user.get_full_name() or request.user.get_username(),
      "email": getattr(request.user, "email", ""),
      "roles": roles,
      "capabilities": {"read": True, "write": is_admin, "admin": is_admin},
      "legacy_url": "/legacy/",
    })


class OverviewAPIView(APIView):
  authentication_classes = [HybridAuthentication]
  permission_classes = [IsAuthenticated]

  def get(self, request):
    return Response({
      "generated_at": timezone.now().isoformat(),
      "counts": {
        "scenes": _count_model("Scene"),
        "cameras": _count_model("Cam"),
        "sensors": _count_model("SingletonSensor"),
        "assets": _count_model("Asset3D"),
        "regions": _count_model("Region"),
        "tripwires": _count_model("Tripwire"),
      },
      "health": {"database": "ok"},
      "history": {
        "available": False,
        "reason": "historian_not_configured",
      },
    })
