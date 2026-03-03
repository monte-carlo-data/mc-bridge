"""Security utilities for MC Bridge."""

from fnmatch import fnmatch

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

# Allowed origins for CORS and request validation
ALLOWED_ORIGINS = [
    "https://getmontecarlo.com",
    "https://*.getmontecarlo.com",
    "https://app.getmontecarlo.com",
    "https://local.getmontecarlo.com:3000",
    "http://localhost:3000",  # Local MC development
    "http://localhost:5173",  # Vite dev server
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]


def is_origin_allowed(origin: str | None) -> bool:
    """Check if the given origin is allowed."""
    if not origin:
        return True  # Allow requests without Origin header (e.g., curl, direct browser)

    for pattern in ALLOWED_ORIGINS:
        if fnmatch(origin, pattern):
            return True
    return False


class OriginValidationMiddleware(BaseHTTPMiddleware):
    """Middleware to validate request origins."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        origin = request.headers.get("origin")

        # Skip validation for health check endpoint
        if request.url.path == "/health":
            return await call_next(request)

        if not is_origin_allowed(origin):
            return JSONResponse(
                status_code=403,
                content={"error": "Forbidden", "detail": "Origin not allowed"},
            )

        return await call_next(request)


CORS_ORIGIN_REGEX = r"^https://([a-zA-Z0-9-]+\.)?getmontecarlo\.com$"

CORS_EXTRA_ORIGINS = [
    "https://local.getmontecarlo.com:3000",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
