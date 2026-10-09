import asyncio
import datetime
import logging
import time
from typing import Any, Dict, List, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class GoGuardError(Exception):
    """Base exception for GoGuard API errors."""
    pass


class GoGuardAuthError(GoGuardError):
    """Raised when authentication fails."""
    pass


class GoGuardNotFoundError(GoGuardError):
    """Raised when a requested resource is not found."""
    pass


class GoGuardAPIError(GoGuardError):
    """Raised when API returns a non-success response."""
    def __init__(self, status_code: int, message: str, response_body: Any = None):
        self.status_code = status_code
        self.message = message
        self.response_body = response_body

        detail = ""
        if response_body:
            try:
                if isinstance(response_body, str):
                    parsed = json.loads(response_body)
                else:
                    parsed = response_body
                if isinstance(parsed, dict):
                    detail = (
                        parsed.get("detail")
                        or parsed.get("message")
                        or parsed.get("error")
                        or parsed.get("msg")
                        or str(parsed)
                    )
                else:
                    detail = str(response_body)
            except Exception:
                detail = str(response_body)

        full_msg = f"{message} | {detail}" if detail and detail not in message else message
        super().__init__(f"GoGuard API Error ({status_code}): {full_msg}")


class GoGuardConnectionError(GoGuardError):
    """Raised on network or connection errors."""
    pass


class GoGuardClient:
    """
    Async client for GoGuard Panel API 1.0.
    Handles automatic authentication, token management, and auto-refresh on 401 Unauthorized.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        sub_url_template: str = "{base_url}/sub/{username}",
        timeout: float = 15.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.sub_url_template = sub_url_template
        self.timeout = timeout

        self._token: Optional[str] = None
        self._token_expires_at: Optional[float] = None
        self._auth_lock = asyncio.Lock()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "GoGuard-TelegramBot/1.0",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _parse_expires_at(self, expires_at: Any) -> Optional[float]:
        """Parse expires_at timestamp which could be int/float epoch or ISO 8601 string."""
        if not expires_at:
            return None
        if isinstance(expires_at, (int, float)):
            return float(expires_at)
        if isinstance(expires_at, str):
            try:
                # Try epoch numeric string
                return float(expires_at)
            except ValueError:
                pass
            try:
                # Try ISO format
                clean_str = expires_at.replace("Z", "+00:00")
                dt = datetime.datetime.fromisoformat(clean_str)
                return dt.timestamp()
            except Exception:
                logger.warning(f"Failed to parse expires_at string: {expires_at}")
        return None

    async def login(self) -> str:
        """
        Authenticate with POST /api/admins/token.
        Payload: {"username": "...", "password": "..."}
        Returns: Bearer token string.
        """
        async with self._auth_lock:
            client = await self._get_client()
            url = "/api/admins/token"
            payload = {
                "username": self.username,
                "password": self.password,
            }

            try:
                logger.info(f"Authenticating GoGuard admin: {self.username} at {self.base_url}")
                response = await client.post(url, json=payload)
            except httpx.RequestError as exc:
                logger.error(f"Network error during GoGuard login: {exc}")
                raise GoGuardConnectionError(f"Cannot reach GoGuard panel: {exc}") from exc

            if response.status_code == 401 or response.status_code == 403:
                logger.error(f"Invalid GoGuard credentials for user '{self.username}': {response.text}")
                raise GoGuardAuthError("Invalid GoGuard username or password.")
            elif response.is_error:
                logger.error(f"GoGuard login failed ({response.status_code}): {response.text}")
                raise GoGuardAPIError(response.status_code, "Login failed", response.text)

            try:
                data = response.json()
            except Exception as exc:
                raise GoGuardAPIError(response.status_code, "Invalid JSON received from login endpoint", response.text) from exc

            token = data.get("token") or data.get("access_token")
            if not token:
                raise GoGuardAuthError(f"Token not found in login response: {data}")

            self._token = token
            self._token_expires_at = self._parse_expires_at(data.get("expires_at"))
            logger.info("Successfully authenticated with GoGuard Panel API.")
            return token

    async def _ensure_token(self) -> str:
        """Ensure token is valid and not expired."""
        now = time.time()
        # If token exists and is valid for at least 30 more seconds, use it
        if self._token and self._token_expires_at and self._token_expires_at > (now + 30):
            return self._token
        if self._token and not self._token_expires_at:
            # If no expiry provided, assume token is valid until 401
            return self._token

        return await self.login()

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json_data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        retry_on_401: bool = True,
    ) -> Any:
        """
        Execute an authenticated request to GoGuard API with automatic 401 token refresh.
        """
        token = await self._ensure_token()
        client = await self._get_client()

        headers = {
            "Authorization": f"Bearer {token}",
        }

        try:
            response = await client.request(
                method=method,
                url=endpoint,
                json=json_data,
                params=params,
                headers=headers,
            )
        except httpx.RequestError as exc:
            logger.error(f"Network error during GoGuard request {method} {endpoint}: {exc}")
            raise GoGuardConnectionError(f"Connection to GoGuard failed: {exc}") from exc

        # Handle 401 Unauthorized -> Refresh token and retry once
        if response.status_code == 401 and retry_on_401:
            logger.warning("Received 401 Unauthorized from GoGuard. Refreshing token and retrying...")
            self._token = None
            token = await self.login()
            headers["Authorization"] = f"Bearer {token}"

            try:
                response = await client.request(
                    method=method,
                    url=endpoint,
                    json=json_data,
                    params=params,
                    headers=headers,
                )
            except httpx.RequestError as exc:
                raise GoGuardConnectionError(f"Connection to GoGuard failed on retry: {exc}") from exc

        if response.status_code == 404:
            raise GoGuardNotFoundError(f"Resource not found: {endpoint}")

        if response.is_error:
            logger.error(f"GoGuard API error ({response.status_code}) on {method} {endpoint}: {response.text}")
            raise GoGuardAPIError(
                status_code=response.status_code,
                message=f"Request to {endpoint} failed with status {response.status_code}",
                response_body=response.text,
            )

        if not response.content:
            return {}

        try:
            return response.json()
        except Exception:
            return response.text

    # =========================================================================
    # Subscription Endpoints
    # =========================================================================

    async def get_services(self) -> List[Dict[str, Any]]:
        """
        Fetch list of available panel services from GET /api/services.
        """
        try:
            res = await self._request("GET", "/api/services")
            if isinstance(res, dict) and "items" in res:
                return res["items"]
            elif isinstance(res, list):
                return res
        except Exception as exc:
            logger.warning(f"Failed to fetch GoGuard services: {exc}")
        return []

    async def create_subscription(
        self,
        username: str,
        data_limit: int,
        expire: int,
        status: str = "active",
        note: str = "",
        services: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new subscription via POST /api/subscriptions.

        Includes required 'services' field (e.g. [1]) as required by GoGuard/GuardCore panel.
        """
        service_ids = services if services is not None else settings.GOGUARD_DEFAULT_SERVICES
        if isinstance(service_ids, int):
            service_ids = [service_ids]
        elif isinstance(service_ids, str):
            service_ids = [int(s.strip()) for s in service_ids.replace("[", "").replace("]", "").split(",") if s.strip()]
        elif not service_ids:
            service_ids = [1]

        clean_services = [int(s) for s in service_ids]

        payload = {
            "username": username,
            "data_limit": int(data_limit),
            "expire": int(expire),
            "limit_usage": int(data_limit),
            "limit_expire": int(expire),
            "services": clean_services,
            "service_ids": clean_services,
            "status": status,
            "note": note,
        }
        logger.info(
            f"Creating GoGuard subscription for '{username}': "
            f"data_limit={data_limit} bytes ({data_limit / (1024**3):.2f} GB), expire={expire}, services={clean_services}"
        )
        result = await self._request("POST", "/api/subscriptions", json_data=payload)
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
            return result[0]
        return result if isinstance(result, dict) else {"response": result}

    async def get_subscription(self, username: str) -> Dict[str, Any]:
        """
        Get subscription details via search query on GET /api/subscriptions or /api/subscriptions/{username}.
        """
        try:
            res = await self._request("GET", "/api/subscriptions", params={"search": username})
            if isinstance(res, dict) and "items" in res:
                for item in res["items"]:
                    if item.get("username") == username:
                        return item
        except Exception as exc:
            logger.debug(f"Search query failed: {exc}")

        try:
            result = await self._request("GET", f"/api/subscriptions/{username}")
            if isinstance(result, dict) and "username" in result:
                return result
        except Exception:
            pass

        return {}

    async def update_subscription(
        self,
        username: str,
        data_limit: Optional[int] = None,
        expire: Optional[int] = None,
        status: Optional[str] = None,
        note: Optional[str] = None,
        services: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Update an existing subscription via PUT /api/subscriptions/{username}.
        """
        payload: Dict[str, Any] = {}
        if data_limit is not None:
            payload["data_limit"] = int(data_limit)
            payload["limit_usage"] = int(data_limit)
        if expire is not None:
            payload["expire"] = int(expire)
            payload["limit_expire"] = int(expire)
        if status is not None:
            payload["status"] = status
        if note is not None:
            payload["note"] = note
        if services is not None:
            payload["services"] = [int(s) for s in services]
            payload["service_ids"] = [int(s) for s in services]

        result = await self._request("PUT", f"/api/subscriptions/{username}", json_data=payload)
        return result if isinstance(result, dict) else {}

    async def reset_subscription(self, username: str) -> Dict[str, Any]:
        """
        Reset usage traffic for a subscription via POST /api/subscriptions/{username}/reset.
        """
        result = await self._request("POST", f"/api/subscriptions/{username}/reset")
        return result if isinstance(result, dict) else {}

    async def delete_subscription(self, username: str) -> bool:
        """
        Delete a subscription via DELETE /api/subscriptions with {"usernames": [username]}.
        """
        try:
            await self._request("DELETE", "/api/subscriptions", json_data={"usernames": [username]})
            return True
        except Exception:
            try:
                await self._request("DELETE", f"/api/subscriptions/{username}")
                return True
            except Exception as exc:
                logger.warning(f"Failed to delete subscription '{username}': {exc}")
                return False

    def get_subscription_url(self, username: str, api_response: Optional[Dict[str, Any]] = None) -> str:
        """
        Resolve the subscription URL:
        1. Checks if api_response contains 'subscription_link', 'subscription_url', 'sub_url', or 'link'.
        2. Falls back to formatting sub_url_template with base_url and username.
        """
        if api_response and isinstance(api_response, dict):
            for key in ("subscription_link", "subscription_url", "sub_url", "link", "url"):
                val = api_response.get(key)
                if val and isinstance(val, str) and val.startswith("http"):
                    return val.strip().strip("`'\"")

        raw_url = self.sub_url_template.format(
            base_url=self.base_url,
            username=username,
        )
        return raw_url.strip().strip("`'\"")

    async def health_check(self) -> bool:
        """
        Test API connection and authentication.
        """
        try:
            await self._ensure_token()
            return True
        except Exception as exc:
            logger.error(f"GoGuard health check failed: {exc}")
            return False
