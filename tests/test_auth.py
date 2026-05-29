"""
Tests básicos para los endpoints de autenticación.

Para correr:
    cd backend
    pytest tests/ -v
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock


from app.main import app


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def mock_db():
    """Simula respuestas de Supabase sin necesitar conexión real."""
    with patch("app.api.v1.endpoints.auth.get_supabase") as mock:
        yield mock


@pytest.mark.asyncio
async def test_register_success(mock_db):
    """Un usuario nuevo puede registrarse y recibe un token."""
    mock_client = MagicMock()
    mock_db.return_value = mock_client

    # Simula que el email NO existe todavía
    mock_client.table().select().eq().execute.return_value = MagicMock(data=[])

    # Simula inserción exitosa
    mock_client.table().insert().execute.return_value = MagicMock(
        data=[{"id": "user-123", "name": "Jose", "email": "jose@test.com"}]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/auth/register", json={
            "name": "Jose",
            "email": "jose@test.com",
            "password": "password123",
        })

    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["user_id"] == "user-123"


@pytest.mark.asyncio
async def test_register_duplicate_email(mock_db):
    """No se puede registrar un email que ya existe."""
    mock_client = MagicMock()
    mock_db.return_value = mock_client

    # Simula que el email YA existe
    mock_client.table().select().eq().execute.return_value = MagicMock(
        data=[{"id": "existing-user"}]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/auth/register", json={
            "name": "Jose",
            "email": "jose@test.com",
            "password": "password123",
        })

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_health_check():
    """El endpoint raíz responde correctamente."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
