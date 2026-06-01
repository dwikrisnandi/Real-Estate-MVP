"""
Enterprise Decorators
=====================
Robust decorators for error handling, retries, and network stability.
"""

import asyncio
import functools
from loguru import logger
from playwright.async_api import TimeoutError as PlaywrightTimeout

def with_retry(max_retries: int = 3, delay: float = 2.0, exceptions=(Exception,)):
    """
    Retry a function execution automatically upon failure.
    
    Args:
        max_retries (int): Maximum number of retries before giving up.
        delay (float): Delay in seconds between retries.
        exceptions (tuple): Exceptions to catch and retry on.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    logger.warning(
                        f"Attempt {attempt}/{max_retries} failed for '{func.__name__}': {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
            logger.error(f"All {max_retries} attempts failed for '{func.__name__}'")
            raise last_exception
        return wrapper
    return decorator

def safe_execute(default_return=None):
    """
    Wrap function in a try-except block and return a default value on failure,
    preventing the entire bot/scraper from crashing due to minor element issues.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in '{func.__name__}': {e}")
                return default_return
        return wrapper
    return decorator
