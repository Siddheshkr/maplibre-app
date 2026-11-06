from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client() -> TestClient:
    settings = Settings(
        _env_file=None,
        database_url=None,
        database_host=None,
        database_name=None,
        database_user=None,
        database_password=None,
        database_schemas="public",
        environment="test",
    )
    return TestClient(create_app(settings))


def test_health_reports_missing_database() -> None:
    with make_client() as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "not_configured"


def test_layers_returns_actionable_error_without_database() -> None:
    with make_client() as client:
        response = client.get("/api/layers")

    assert response.status_code == 503
    assert "DATABASE" in response.json()["detail"]


def test_layer_listing_can_be_refreshed() -> None:
    with make_client() as client:
        response = client.get("/api/layers?refresh=true")
    assert response.status_code == 503


def test_invalid_layer_id_is_rejected_before_database_access() -> None:
    with make_client() as client:
        response = client.get("/api/tiles/public%3Bdrop/0/0/0.pbf")
    assert response.status_code == 400


def test_invalid_tile_coordinates_are_rejected() -> None:
    with make_client() as client:
        response = client.get("/api/tiles/public.districts/0/1/0.pbf")
    assert response.status_code == 400
