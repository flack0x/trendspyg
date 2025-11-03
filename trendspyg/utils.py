"""Utility functions for trendspy."""

import os
import time
from datetime import datetime


def get_timestamp():
    """Get current timestamp in YYYYMMDD-HHMMSS format."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def ensure_dir(directory):
    """Ensure directory exists, create if it doesn't."""
    os.makedirs(directory, exist_ok=True)
    return directory


def rate_limit(delay=1.0):
    """Simple rate limiting decorator."""
    def decorator(func):
        last_called = [0.0]

        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            if elapsed < delay:
                time.sleep(delay - elapsed)
            result = func(*args, **kwargs)
            last_called[0] = time.time()
            return result
        return wrapper
    return decorator
