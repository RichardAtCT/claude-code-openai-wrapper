import os
from typing import Optional
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse


def get_rate_limit_key(request: Request) -> str:
    """Get the rate limiting key (IP address) from the request."""
    return get_remote_address(request)


def create_rate_limiter() -> Optional[Limiter]:
    """Create and configure the rate limiter based on environment variables."""
    rate_limit_enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in (
        "true",
        "1",
        "yes",
        "on",
    )

    if not rate_limit_enabled:
        return None

    # Create limiter with IP-based identification
    limiter = Limiter(
        key_func=get_rate_limit_key, default_limits=[]  # We'll apply limits per endpoint
    )

    return limiter


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom rate limit exceeded handler that returns JSON error response."""
    # Calculate retry after based on rate limit window (default 60 seconds)
    retry_after = 60
    response = JSONResponse(
        status_code=429,
        content={
            "error": {
                "message": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                "type": "rate_limit_exceeded",
                "code": "too_many_requests",
                "retry_after": retry_after,
            }
        },
        headers={"Retry-After": str(retry_after)},
    )
    return response


def get_rate_limit_for_endpoint(endpoint: str) -> str:
    """Get rate limit string for specific endpoint based on environment variables."""
    # Default rate limits
    defaults = {
        "chat": "10/minute",
        "debug": "2/minute",
        "auth": "10/minute",
        "session": "15/minute",
        "health": "30/minute",
        "general": "30/minute",
    }

    # Environment variable mappings
    env_mappings = {
        "chat": "RATE_LIMIT_CHAT_PER_MINUTE",
        "debug": "RATE_LIMIT_DEBUG_PER_MINUTE",
        "auth": "RATE_LIMIT_AUTH_PER_MINUTE",
        "session": "RATE_LIMIT_SESSION_PER_MINUTE",
        "health": "RATE_LIMIT_HEALTH_PER_MINUTE",
        "general": "RATE_LIMIT_PER_MINUTE",
    }

    # Get rate limit from environment or use default
    env_var = env_mappings.get(endpoint, "RATE_LIMIT_PER_MINUTE")
    rate_per_minute = int(os.getenv(env_var, defaults.get(endpoint, "30").split("/")[0]))

    return f"{rate_per_minute}/minute"


def rate_limit_endpoint(endpoint: str):
    """Decorator factory for applying rate limits to endpoints."""

    def decorator(func):
        if limiter:
            return limiter.limit(get_rate_limit_for_endpoint(endpoint))(func)
        return func

    return decorator


# Create the global limiter instance
limiter = create_rate_limiter()
