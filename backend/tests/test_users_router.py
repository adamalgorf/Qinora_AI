import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qinora.infrastructure.passwords import hash_password
from qinora.infrastructure.sqlite import SQLiteDatabase, SQLiteUserRepository
from qinora.interfaces.http.app import create_app


def _create_user(
    sqlite_path: Path, *, email: str, password: str, roles: tuple[str, ...]
) -> str:
    async def _run() -> str:
        database = SQLiteDatabase(sqlite_path)
        repository = SQLiteUserRepository(database)
        user = await repository.create_user(
            email=email,
            full_name="Test User",
            password_hash=hash_password(password),
            roles=roles,
        )
        return user.id

    return asyncio.run(_run())


def _login(client: TestClient, *, email: str, password: str) -> str:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def admin_client(monkeypatch, tmp_path) -> tuple[TestClient, dict[str, str], str]:
    sqlite_path = tmp_path / "qinora_test.sqlite3"
    monkeypatch.setenv("QINORA_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("QINORA_REQUIRE_AUTH", "true")
    admin_id = _create_user(
        sqlite_path, email="admin@example.com", password="correct-horse", roles=("admin",)
    )
    _create_user(
        sqlite_path, email="shipper@example.com", password="correct-horse", roles=("shipper",)
    )
    client = TestClient(create_app())
    admin_token = _login(client, email="admin@example.com", password="correct-horse")
    shipper_token = _login(client, email="shipper@example.com", password="correct-horse")
    return (
        client,
        {
            "admin": f"Bearer {admin_token}",
            "shipper": f"Bearer {shipper_token}",
        },
        admin_id,
    )


def test_non_admin_cannot_list_users(admin_client) -> None:
    client, tokens, _ = admin_client

    response = client.get("/users", headers={"authorization": tokens["shipper"]})

    assert response.status_code == 403


def test_admin_can_list_users(admin_client) -> None:
    client, tokens, _ = admin_client

    response = client.get("/users", headers={"authorization": tokens["admin"]})

    assert response.status_code == 200
    emails = {user["email"] for user in response.json()}
    assert emails == {"admin@example.com", "shipper@example.com"}


def test_admin_can_create_user(admin_client) -> None:
    client, tokens, _ = admin_client

    response = client.post(
        "/users",
        json={
            "email": "carrier@example.com",
            "full_name": "Carrier User",
            "roles": ["carrier"],
            "temporary_password": "temporary123",
        },
        headers={"authorization": tokens["admin"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "carrier@example.com"
    assert body["roles"] == ["carrier"]
    assert body["is_active"] is True

    login_response = client.post(
        "/auth/login",
        json={"email": "carrier@example.com", "password": "temporary123"},
    )
    assert login_response.status_code == 200


def test_admin_cannot_create_duplicate_email(admin_client) -> None:
    client, tokens, _ = admin_client

    response = client.post(
        "/users",
        json={
            "email": "shipper@example.com",
            "roles": ["shipper"],
            "temporary_password": "temporary123",
        },
        headers={"authorization": tokens["admin"]},
    )

    assert response.status_code == 409


def test_admin_can_update_roles_and_deactivate_other_user(admin_client) -> None:
    client, tokens, _ = admin_client
    users = client.get("/users", headers={"authorization": tokens["admin"]}).json()
    shipper_id = next(user["id"] for user in users if user["email"] == "shipper@example.com")

    response = client.patch(
        f"/users/{shipper_id}",
        json={"roles": ["carrier", "admin"], "is_active": False},
        headers={"authorization": tokens["admin"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert sorted(body["roles"]) == ["admin", "carrier"]
    assert body["is_active"] is False


def test_admin_cannot_deactivate_self(admin_client) -> None:
    client, tokens, admin_id = admin_client

    response = client.patch(
        f"/users/{admin_id}",
        json={"is_active": False},
        headers={"authorization": tokens["admin"]},
    )

    assert response.status_code == 400


def test_admin_can_reset_another_users_password(admin_client) -> None:
    client, tokens, _ = admin_client
    users = client.get("/users", headers={"authorization": tokens["admin"]}).json()
    shipper_id = next(user["id"] for user in users if user["email"] == "shipper@example.com")

    response = client.post(
        f"/users/{shipper_id}/reset-password",
        json={"temporary_password": "brand-new-pass"},
        headers={"authorization": tokens["admin"]},
    )
    assert response.status_code == 204

    login_response = client.post(
        "/auth/login",
        json={"email": "shipper@example.com", "password": "brand-new-pass"},
    )
    assert login_response.status_code == 200
