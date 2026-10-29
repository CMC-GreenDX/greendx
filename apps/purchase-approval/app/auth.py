"""Verifies the Keycloak access token again inside the service (the gateway already did once)."""

from __future__ import annotations

import os
from dataclasses import dataclass

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OpenIdConnect

JWKS_URL = os.environ.get("JWKS_URL", "http://keycloak:8080/realms/ecotrace/protocol/openid-connect/certs")
ISSUER = os.environ.get("JWT_ISSUER", "http://localhost:8080/realms/ecotrace")

_jwks = jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=300)

# Both schemes read the same Authorization header. They are declared so that the OpenAPI document
# (and the /api-docs page) offers both ways in: log in with Keycloak, or paste an access token.
_token = HTTPBearer(auto_error=False, scheme_name="accessToken", description="Keycloak access token of the ecotrace realm")
_login = OpenIdConnect(openIdConnectUrl=f"{ISSUER}/.well-known/openid-configuration", auto_error=False,
                       scheme_name="keycloak", description="Log in with Keycloak (client ecotrace-portal, PKCE)")


@dataclass(frozen=True)
class User:
    username: str
    tenant_id: str
    roles: frozenset[str]

    def require(self, role: str) -> None:
        if role not in self.roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires the {role} role")


def current_user(credentials: HTTPAuthorizationCredentials | None = Security(_token),
                 _: str | None = Security(_login)) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = credentials.credentials
    try:
        key = _jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], issuer=ISSUER,
                            options={"verify_aud": False, "require": ["exp", "iss"]})
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc
    tenant_id = claims.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token has no tenant_id claim")
    return User(username=claims.get("preferred_username", "unknown"), tenant_id=tenant_id,
                roles=frozenset(claims.get("realm_access", {}).get("roles", [])))
