import os
import functools
from typing import Optional
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse, Response


def get_rate_limit_key(request: Request) -> str:
    """Get the rate limiting key (IP address) from the request.

    When TRUSTED_PROXIES is configured and the direct peer IP is in that list,
    the rightmost non-trusted IP from X-Forwarded-For is used so that the real
    client is rate-limited rather than the proxy.  When the peer is not trusted,
    X-Forwarded-For is ignored entirely to prevent IP-spoofing attacks.
    """
    from src.constants import TRUSTED_PROXIES

    client_ip = request.client.host if request.client else "127.0.0.1"

    if not TRUSTED_PROXIES or client_ip not in TRUSTED_PROXIES:
        return client_ip

    # Peer is a trusted proxy — read X-Forwarded-For
    xff = request.headers.get("x-forwarded-for", "")
    if not xff:
        return client_ip  # fallback: no upstream IP available

    # Return rightmost non-trusted IP (closest to the real client)
    ips = [ip.strip() for ip in xff.split(",")]
    for ip in reversed(ips):
        if ip not in TRUSTED_PROXIES:
            return ip

    return client_ip  # all IPs in chain are trusted, fallback to peer


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
    limiter = Limiter(key_func=get_rate_limit_key, default_limits=[])

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
    """Decorator factory for applying rate limits to endpoints.

    Wraps the endpoint with slowapi rate limiting and injects X-RateLimit-Limit
    into the response headers so callers can observe the limit value.

    Clears any previously registered limits for the route before registering new
    ones so that module reloads (common in tests) do not accumulate duplicate
    limit entries that would be applied multiplicatively.
    """
    rate_limit_str = get_rate_limit_for_endpoint(endpoint)
    # Parse requests-per-minute from the rate limit string (e.g. "30/minute")
    limit_value = rate_limit_str.split("/")[0]

    def decorator(func):
        if not limiter:
            # Rate limiting disabled — return the original function unchanged.
            return func

        # Clear any stale limit registrations for this route that may have
        # been added by previous module loads (avoids duplicate-counting).
        func_name = f"{func.__module__}.{func.__name__}"
        if func_name in limiter._route_limits:
            limiter._route_limits[func_name] = []

        limited_func = limiter.limit(rate_limit_str)(func)

        @functools.wraps(limited_func)
        async def wrapper(*args, **kwargs):
            result = await limited_func(*args, **kwargs)
            # Inject X-RateLimit-Limit header so tests and clients can observe the limit.
            if isinstance(result, Response):
                result.headers["X-RateLimit-Limit"] = limit_value
            return result

        return wrapper

    return decorator


# Create the global limiter instance
limiter = create_rate_limiter()
