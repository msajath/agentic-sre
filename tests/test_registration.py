"""Public registration creates read-only accounts without role escalation."""

from src.api.auth_router import registration_attempt_limiter


def test_registration_creates_viewer_and_rejects_duplicate_identity(client):
    key = ("testclient", "registration")
    registration_attempt_limiter.clear(key)
    account = {"username": "new_sre", "email": "new.sre@example.com",
               "full_name": "New SRE", "password": "new-unique-credential-2026"}
    try:
        response = client.post("/api/v1/auth/register", json=account, headers={"Authorization": ""})
        assert response.status_code == 201, response.text
        token = response.json()
        assert token["role"] == "VIEWER"
        assert token["username"] == "new_sre"
        profile = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token['access_token']}"})
        assert profile.status_code == 200
        assert profile.json()["email"] == account["email"]
        assert profile.json()["role"] == "VIEWER"
        settings_response = client.post(
            "/api/v1/settings",
            headers={"Authorization": f"Bearer {token['access_token']}"},
            json={"error_rate_threshold": 0.1, "latency_p95_threshold_ms": 1200},
        )
        assert settings_response.status_code == 403

        assert client.post("/api/v1/auth/register", json=account).status_code == 409
        duplicate_email = {**account, "username": "another_sre"}
        assert client.post("/api/v1/auth/register", json=duplicate_email).status_code == 409
    finally:
        registration_attempt_limiter.clear(key)


def test_registration_cannot_choose_privileged_role(client):
    key = ("testclient", "registration")
    registration_attempt_limiter.clear(key)
    try:
        account = {"username": "would_be_admin", "email": "admin2@example.com",
                   "full_name": "Would Be Admin", "password": "new-unique-credential-2026"}
        response = client.post("/api/v1/auth/register", json={**account, "role": "ADMIN"})
        assert response.status_code == 422
        response = client.post("/api/v1/auth/register", json={**account, "password": "short"})
        assert response.status_code == 422
    finally:
        registration_attempt_limiter.clear(key)
