import asyncio
from typing import Callable, Any

class PipelineError(Exception):
    """Base exception class for all scraper pipeline errors."""
    pass

class NetworkTimeoutError(PipelineError):
    """Raised when a network request times out."""
    pass

class ConnectionRefusedError(PipelineError):
    """Raised when connection is refused or unreachable."""
    pass

class DNSResolutionError(PipelineError):
    """Raised when domain name resolution fails."""
    pass

def handle_download_exceptions(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator utility to translate low-level networking and connection 
    exceptions into descriptive pipeline errors.
    """
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.TimeoutError as e:
            raise NetworkTimeoutError(f"Request timed out during operation: {e}") from e
        except ConnectionError as e:
            raise ConnectionRefusedError(f"Connection failed or was refused: {e}") from e
        except OSError as e:
            err_str = str(e).lower()
            if "getaddrinfo" in err_str or "name or service not known" in err_str:
                raise DNSResolutionError(f"DNS resolution failed: {e}") from e
            raise PipelineError(f"OS-level network error encountered: {e}") from e
        except Exception as e:
            if isinstance(e, PipelineError):
                raise
            raise PipelineError(f"Unexpected pipeline error: {e}") from e
    return wrapper
