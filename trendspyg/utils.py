"""Utility functions for trendspy."""

import os
import time
from datetime import datetime
from typing import Callable, Any, TypeVar, cast
from functools import wraps

# Type variable for generic function
F = TypeVar('F', bound=Callable[..., Any])


def get_timestamp() -> str:
    """Get current timestamp in YYYYMMDD-HHMMSS format."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def ensure_dir(directory: str) -> str:
    """Ensure directory exists, create if it doesn't."""
    os.makedirs(directory, exist_ok=True)
    return directory


def rate_limit(delay: float = 1.0) -> Callable[[F], F]:
    """Simple rate limiting decorator."""
    def decorator(func: F) -> F:
        last_called = [0.0]

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            elapsed = time.time() - last_called[0]
            if elapsed < delay:
                time.sleep(delay - elapsed)
            result = func(*args, **kwargs)
            last_called[0] = time.time()
            return result
        return cast(F, wrapper)
    return decorator
