from __future__ import annotations

import hashlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from avocat_expert.api.app import create_app
from avocat_expert.config import Settings, get_settings

TOKEN = "jeton-de-test-non-secret"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", database_url="", dev_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest()
    )
    with TestClient(app) as test_client:
        yield test_client


def test_health_is_public(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"


@pytest.mark.parametrize("path", ["/v1/search", "/v1/answer", "/v1/citations/verify"])
def test_authentication_precedes_any_other_dependency(client: TestClient, path: str) -> None:
    # Sans base configurée, une dépendance évaluée avant l'authentification renverrait 503.
    assert client.post(path, json={}).status_code == 401
    assert client.post(path, json={}, headers={"Authorization": "Bearer mauvais"}).status_code == 401


def test_valid_token_passes_authentication(client: TestClient) -> None:
    # Authentification réussie : l'échec suivant provient de l'absence de base configurée.
    response = client.post("/v1/search", json={"query": "durée"}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 503
    assert response.json()["detail"] == "base de données non configurée"


def test_dev_token_forbidden_outside_local() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", auth_mode="dev_token")


def test_oidc_mode_fails_closed() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(environment="test", auth_mode="oidc")
    with TestClient(app) as test_client:
        response = test_client.post("/v1/search", json={"query": "durée"}, headers={"Authorization": "Bearer x"})
    assert response.status_code == 503
