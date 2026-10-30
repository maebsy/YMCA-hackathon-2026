from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.explain_jobs.config import JobSettings

bearer = HTTPBearer(auto_error=False)


class SupabaseAuth:
    """Validate the access token with the configured project's Auth server, never decode-and-trust."""

    def __init__(self, settings: JobSettings, client: httpx.AsyncClient):
        settings.validate_auth()
        self.url = settings.supabase_url.rstrip("/") + "/auth/v1/user"
        self.key = settings.supabase_publishable_key
        self.client = client

    async def verify(self, token: str) -> UUID:
        try:
            response = await self.client.get(
                self.url, headers={"apikey": self.key, "Authorization": f"Bearer {token}"},
                timeout=10, follow_redirects=False,
            )
        except httpx.HTTPError:
            raise HTTPException(503, "AUTH_UNAVAILABLE") from None
        if response.status_code in (401, 403):
            raise HTTPException(401, "INVALID_ACCESS_TOKEN", headers={"WWW-Authenticate": "Bearer"})
        if response.status_code != 200:
            raise HTTPException(503, "AUTH_UNAVAILABLE")
        try:
            user = response.json()
            # Anonymous Supabase users/claim tokens cannot purchase GPU access through this API.
            if user.get("is_anonymous") is True:
                raise HTTPException(403, "LOGIN_REQUIRED")
            return UUID(user["id"])
        except (ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(503, "AUTH_INVALID_RESPONSE") from None


async def current_user(
    request: Request,
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> UUID:
    if credential is None or credential.scheme.lower() != "bearer" or len(credential.credentials) > 8192:
        raise HTTPException(401, "BEARER_REQUIRED", headers={"WWW-Authenticate": "Bearer"})
    return await request.app.state.job_auth.verify(credential.credentials)


UserDep = Annotated[UUID, Depends(current_user)]
