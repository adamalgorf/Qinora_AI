import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qinora.infrastructure.passwords import hash_password
from qinora.infrastructure.sqlite import SQLiteDatabase, SQLiteUserRepository
from qinora.interfaces.http.app import create_app


def _create_user(
    sqlite_path: Path,
    *,
    email: str,
    password: str,
    roles: tuple[str, ...] = ("admin",),
    is_active: bool = True,
) -> None:
    async def _run() -> None:
        database = SQLiteDatabase(sqlite_path)
        repository = SQLiteUserRepository(database)
        user = await repository.create_user(
            email=email,
            full_name="Test User",
            password_hash=hash_password(password),
            roles=roles,
        )
        if not is_active:
            await repository.set_active(user.id, False)

    asyncio.run(_run())


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("QINORA_SQLITE_PATH", str(tmp_path / "qinora_test.sqlite3"))
    return TestClient(create_app())


def test_auth_config_reports_no_login_required_by_default(client: TestClient) -> None:
    response = client.get("/auth/config")

    assert response.status_code == 200
    assert response.json() == {"login_required": False}


def test_requests_work_without_auth_when_no_password_configured(client: TestClient) -> None:
    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["user_id"] == "dev-user"


@pytest.fixture
def protected_client(monkeypatch, tmp_path) -> TestClient:
    sqlite_path = tmp_path / "qinora_test.sqlite3"
    monkeypatch.setenv("QINORA_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("QINORA_REQUIRE_AUTH", "true")
    _create_user(sqlite_path, email="admin@example.com", password="correct-horse")
    return TestClient(create_app())


def test_auth_config_reports_login_required_when_configured(
    protected_client: TestClient,
) -> None:
    response = protected_client.get("/auth/config")

    assert response.json() == {"login_required": True}


def test_requests_without_token_are_rejected_when_password_configured(
    protected_client: TestClient,
) -> None:
    response = protected_client.get("/auth/me")

    assert response.status_code == 401


def test_login_with_wrong_password_is_rejected(protected_client: TestClient) -> None:
    response = protected_client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "wrong"}
    )

    assert response.status_code == 401


def test_login_with_unknown_email_is_rejected(protected_client: TestClient) -> None:
    response = protected_client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )

    assert response.status_code == 401


def test_login_with_correct_password_grants_access(protected_client: TestClient) -> None:
    login_response = protected_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "correct-horse"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    me_response = protected_client.get(
        "/auth/me", headers={"authorization": f"Bearer {token}"}
    )
    assert me_response.status_code == 200
    assert me_response.json()["roles"] == ["admin"]


def test_inactive_user_cannot_login(monkeypatch, tmp_path) -> None:
    sqlite_path = tmp_path / "qinora_test.sqlite3"
    monkeypatch.setenv("QINORA_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("QINORA_REQUIRE_AUTH", "true")
    _create_user(
        sqlite_path,
        email="disabled@example.com",
        password="correct-horse",
        is_active=False,
    )
    client = TestClient(create_app())

    response = client.post(
        "/auth/login",
        json={"email": "disabled@example.com", "password": "correct-horse"},
    )
    assert response.status_code == 401


def test_login_supports_non_ascii_passwords(monkeypatch, tmp_path) -> None:
    sqlite_path = tmp_path / "qinora_test.sqlite3"
    monkeypatch.setenv("QINORA_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("QINORA_REQUIRE_AUTH", "true")
    _create_user(sqlite_path, email="admin@example.com", password="testlösen123")
    client = TestClient(create_app())

    wrong = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "fel-lösen"}
    )
    assert wrong.status_code == 401

    correct = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "testlösen123"}
    )
    assert correct.status_code == 200


def test_dev_token_endpoint_disabled_when_password_configured(
    protected_client: TestClient,
) -> None:
    response = protected_client.post("/auth/dev-token", json={})

    assert response.status_code == 404


def test_change_password_flow(protected_client: TestClient) -> None:
    login_response = protected_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "correct-horse"},
    )
    token = login_response.json()["access_token"]
    headers = {"authorization": f"Bearer {token}"}

    change_response = protected_client.post(
        "/auth/change-password",
        json={"current_password": "correct-horse", "new_password": "new-password-123"},
        headers=headers,
    )
    assert change_response.status_code == 204

    old_password_login = protected_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "correct-horse"},
    )
    assert old_password_login.status_code == 401

    new_password_login = protected_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "new-password-123"},
    )
    assert new_password_login.status_code == 200


def test_change_password_rejects_wrong_current_password(protected_client: TestClient) -> None:
    login_response = protected_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "correct-horse"},
    )
    token = login_response.json()["access_token"]

    response = protected_client.post(
        "/auth/change-password",
        json={"current_password": "wrong", "new_password": "new-password-123"},
        headers={"authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
