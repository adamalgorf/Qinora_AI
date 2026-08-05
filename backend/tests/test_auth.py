import pytest
from fastapi.testclient import TestClient

from qinora.interfaces.http.app import create_app


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("QINORA_SQLITE_PATH", str(tmp_path / "qinora.test.sqlite3"))
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
    monkeypatch.setenv("QINORA_SQLITE_PATH", str(tmp_path / "qinora.test.sqlite3"))
    monkeypatch.setenv("QINORA_APP_PASSWORD", "correct-horse")
    return TestClient(create_app())


def test_auth_config_reports_login_required_when_password_set(
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
    response = protected_client.post("/auth/login", json={"password": "wrong"})

    assert response.status_code == 401


def test_login_with_correct_password_grants_access(protected_client: TestClient) -> None:
    login_response = protected_client.post(
        "/auth/login", json={"password": "correct-horse"}
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    me_response = protected_client.get(
        "/auth/me", headers={"authorization": f"Bearer {token}"}
    )
    assert me_response.status_code == 200
    assert me_response.json()["user_id"] == "admin"
    assert me_response.json()["roles"] == ["admin"]


def test_login_supports_non_ascii_passwords(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QINORA_SQLITE_PATH", str(tmp_path / "qinora.test.sqlite3"))
    monkeypatch.setenv("QINORA_APP_PASSWORD", "testlösen123")
    client = TestClient(create_app())

    wrong = client.post("/auth/login", json={"password": "fel-lösen"})
    assert wrong.status_code == 401

    correct = client.post("/auth/login", json={"password": "testlösen123"})
    assert correct.status_code == 200


def test_dev_token_endpoint_disabled_when_password_configured(
    protected_client: TestClient,
) -> None:
    response = protected_client.post("/auth/dev-token", json={})

    assert response.status_code == 404
