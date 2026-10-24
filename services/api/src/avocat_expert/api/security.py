"""Authentification des requêtes.

* ``dev_token`` (local/test uniquement) : jeton porteur comparé, en temps
  constant, à une empreinte SHA-256 fournie par l'environnement ;
* ``oidc`` : non implémenté dans cette tranche — l'application refuse alors
  toute requête authentifiée (fail-closed) plutôt que de laisser passer.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from avocat_expert.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant_id: str | None
    roles: frozenset[str]


def require_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentification requise",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    if settings.auth_mode == "oidc":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "authentification OIDC non encore disponible")
    expected = settings.dev_token_sha256.strip().lower()
    if len(expected) != 64:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "authentification non configurée")
    presented = hashlib.sha256(credentials.credentials.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(presented, expected):
        raise unauthorized
    return Principal(subject="dev", tenant_id=None, roles=frozenset({"READER"}))
