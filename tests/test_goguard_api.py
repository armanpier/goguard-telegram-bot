import json
import pytest
import httpx
from app.services.goguard import (
    GoGuardClient,
    GoGuardAuthError,
    GoGuardAPIError,
    GoGuardNotFoundError,
)


@pytest.mark.asyncio
async def test_goguard_login_success():
    """Verify GoGuard login parses token and expiration."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/admins/token"
        data = json.loads(request.content)
        assert data["username"] == "admin"
        assert data["password"] == "pass123"
        return httpx.Response(
            200,
            json={
                "token": "valid_token_xyz",
                "token_type": "Bearer",
                "expires_at": 1893456000,
            },
        )

    transport = httpx.MockTransport(handler)
    client = GoGuardClient("https://core.erfjab.com", "admin", "pass123")
    client._client = httpx.AsyncClient(transport=transport, base_url="https://core.erfjab.com")

    token = await client.login()
    assert token == "valid_token_xyz"
    assert client._token == "valid_token_xyz"
    assert client._token_expires_at == 1893456000.0
    await client.close()


@pytest.mark.asyncio
async def test_goguard_login_invalid_credentials():
    """Verify GoGuard login handles 401 unauthorized."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Incorrect username or password"})

    transport = httpx.MockTransport(handler)
    client = GoGuardClient("https://core.erfjab.com", "wrong", "wrong")
    client._client = httpx.AsyncClient(transport=transport, base_url="https://core.erfjab.com")

    with pytest.raises(GoGuardAuthError):
        await client.login()

    await client.close()


@pytest.mark.asyncio
async def test_goguard_create_subscription():
    """Verify create_subscription sends correct schema and headers."""
    call_log = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/admins/token":
            return httpx.Response(200, json={"token": "tok_123", "expires_at": 1893456000})

        if request.url.path == "/api/subscriptions":
            call_log.append(request)
            assert request.headers["Authorization"] == "Bearer tok_123"
            payload = json.loads(request.content)
            assert payload["username"] == "john_doe"
            assert payload["data_limit"] == 10737418240  # 10 GB in bytes
            assert payload["expire"] == 1775730000
            assert payload["status"] == "active"
            assert payload["note"] == "Test customer"
            assert payload["services"] == [1]
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "username": "john_doe",
                    "data_limit": 10737418240,
                    "expire": 1775730000,
                    "status": "active",
                    "subscription_url": "https://core.erfjab.com/sub/john_doe",
                },
            )

        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = GoGuardClient("https://core.erfjab.com", "admin", "secret")
    client._client = httpx.AsyncClient(transport=transport, base_url="https://core.erfjab.com")

    res = await client.create_subscription(
        username="john_doe",
        data_limit=10737418240,
        expire=1775730000,
        status="active",
        note="Test customer",
    )
    assert len(call_log) == 1
    assert res["username"] == "john_doe"
    assert res["subscription_url"] == "https://core.erfjab.com/sub/john_doe"

    sub_url = client.get_subscription_url("john_doe", res)
    assert sub_url == "https://core.erfjab.com/sub/john_doe"

    await client.close()


@pytest.mark.asyncio
async def test_goguard_automatic_token_refresh_on_401():
    """Verify that when API returns 401, client transparently re-authenticates and retries."""
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count

        if request.url.path == "/api/admins/token":
            return httpx.Response(200, json={"token": f"fresh_token_{request_count}", "expires_at": 1893456000})

        if request.url.path == "/api/subscriptions":
            request_count += 1
            if request_count == 1:
                # First time: simulate expired token -> 401 Unauthorized
                return httpx.Response(401, json={"detail": "Token expired"})
            else:
                # Second time: should have fresh token header
                assert "Bearer fresh_token" in request.headers["Authorization"]
                return httpx.Response(
                    200,
                    json={
                        "items": [{
                            "username": "john_doe",
                            "data_limit": 10737418240,
                            "used_traffic": 524288000,
                            "status": "active",
                        }]
                    },
                )

        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = GoGuardClient("https://core.erfjab.com", "admin", "secret")
    client._client = httpx.AsyncClient(transport=transport, base_url="https://core.erfjab.com")

    # Set initially stale token
    client._token = "stale_token"
    client._token_expires_at = 1893456000.0

    result = await client.get_subscription("john_doe")
    assert result["username"] == "john_doe"
    assert result["used_traffic"] == 524288000
    assert request_count == 2  # 1st failed with 401, 2nd succeeded after re-login

    await client.close()


@pytest.mark.asyncio
async def test_goguard_delete_subscription():
    """Verify subscription deletion."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/admins/token":
            return httpx.Response(200, json={"token": "tok_123", "expires_at": 1893456000})
        if request.url.path == "/api/subscriptions":
            data = json.loads(request.content)
            assert data["usernames"] == ["user_to_delete"]
            return httpx.Response(200, json={"message": "Subscriptions deleted successfully"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = GoGuardClient("https://core.erfjab.com", "admin", "secret")
    client._client = httpx.AsyncClient(transport=transport, base_url="https://core.erfjab.com")

    deleted = await client.delete_subscription("user_to_delete")
    assert deleted is True

    await client.close()
