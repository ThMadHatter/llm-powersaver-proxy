import secrets

from fastapi import HTTPException, Request, status

from .config import Settings

PUBLIC_PATHS = {"/", "/health/live", "/health/ready", "/docs", "/openapi.json", "/redoc"}


def verify_router_key(request: Request, settings: Settings) -> None:
    if request.url.path in PUBLIC_PATHS:
        return
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    valid = scheme.lower() == "bearer" and secrets.compare_digest(token, settings.router_api_key)
    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key non valida", headers={"WWW-Authenticate": "Bearer"})
